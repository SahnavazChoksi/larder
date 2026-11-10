"""Invoice scanning: read a supplier invoice (photo or PDF) into draft delivery lines.

Reading uses Claude's vision through the Anthropic API when ANTHROPIC_API_KEY is set.
Without a key, the scan is stored and the lines are typed in by hand on the same screen.
"""
import base64
import difflib
import json
import logging
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Item, Vendor
from stock.services import fail, q4

from . import services
from .models import InvoiceScan, PurchaseOrder

log = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_BYTES = 10 * 1024 * 1024
LB_PER_KG = Decimal("2.20462")
PROMPT = (
    "This is a supplier invoice for a restaurant. Read it and reply with JSON only, no other text, in this shape: "
    '{"vendor_name": str, "invoice_number": str, "invoice_date": "YYYY-MM-DD", '
    '"lines": [{"description": str, "quantity": number, "unit": str, "unit_price": number, "line_total": number}]}. '
    "Use the unit as printed (kg, lb, L, case, each…). Leave out tax, delivery and deposit lines. "
    "Use null for anything you can't read."
)


def _call_claude(raw: bytes, content_type: str) -> dict:
    data = base64.b64encode(raw).decode()
    if content_type == "application/pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    else:
        block = {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": data}}
    body = {"model": settings.LARDER_OCR_MODEL, "max_tokens": 2000,
            "messages": [{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
        headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        reply = json.loads(resp.read())
    text = "".join(b.get("text", "") for b in reply.get("content", []) if b.get("type") == "text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON in the reply")
    return json.loads(text[start:end + 1])


def _num(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def match_vendor(name: str | None) -> Vendor | None:
    if not name:
        return None
    vendors = {v.name.lower(): v for v in Vendor.objects.all()}
    hit = difflib.get_close_matches(name.lower(), list(vendors), n=1, cutoff=0.5)
    return vendors[hit[0]] if hit else None


def match_line(description: str, unit: str | None, qty, price, vendor: Vendor | None) -> dict:
    """Find the stock item a printed line refers to and convert lb to kg where needed."""
    pool = Item.objects.filter(kind=Item.Kind.RAW, is_active=True)
    if vendor:
        pool = pool.filter(vendor=vendor) or pool
    names = {i.name.lower(): i for i in pool}
    desc = (description or "").lower()
    best, score = None, 0.0
    for name, item in names.items():
        words = [w for w in name.replace(",", " ").split() if len(w) > 2]
        overlap = sum(1 for w in words if w in desc) / len(words) if words else 0
        ratio = max(overlap, difflib.SequenceMatcher(None, name, desc).ratio())
        if ratio > score:
            best, score = item, ratio
    qty, price = _num(qty), _num(price)
    note = ""
    if best and unit and unit.lower().startswith("lb") and best.unit == "kg" and qty is not None:
        qty, price = q4(qty / LB_PER_KG), (q4(price * LB_PER_KG) if price is not None else None)
        note = f"Converted from {unit} to kg"
    return {
        "text": description or "", "unit_printed": unit or "", "item": best.id if best and score >= 0.45 else None,
        "qty": float(qty) if qty is not None else None, "unit_price": float(price) if price is not None else None,
        "confidence": round(score * 100) if best else 0, "note": note,
    }


def read(scan: InvoiceScan, raw: bytes, content_type: str):
    if not settings.ANTHROPIC_API_KEY:
        scan.engine, scan.message = "manual", "Automatic reading is off (no ANTHROPIC_API_KEY). Type the lines from the invoice."
        return
    try:
        data = _call_claude(raw, content_type)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        log.warning("Invoice reading failed: %s", exc)
        scan.engine, scan.message = "manual", "Couldn't read this invoice automatically. Type the lines in, or try a sharper photo."
        return
    scan.engine = "claude"
    scan.vendor_text = (data.get("vendor_name") or "")[:120]
    scan.vendor = scan.vendor or match_vendor(scan.vendor_text)
    scan.invoice_number = (data.get("invoice_number") or "")[:40]
    try:
        scan.invoice_date = date.fromisoformat(data.get("invoice_date") or "")
    except ValueError:
        scan.invoice_date = None
    scan.lines = [match_line(x.get("description"), x.get("unit"), x.get("quantity"), x.get("unit_price"), scan.vendor)
                  for x in data.get("lines") or []]
    unmatched = sum(1 for x in scan.lines if not x["item"])
    scan.message = f"Read {len(scan.lines)} lines." + (f" {unmatched} need an item chosen." if unmatched else " Check them, then approve.")


def create_scan(location, upload, user, vendor=None) -> InvoiceScan:
    content_type = (upload.content_type or "").split(";")[0]
    if content_type not in ALLOWED_TYPES:
        fail("Upload a photo (JPEG, PNG, WebP) or a PDF of the invoice.")
    if upload.size > MAX_BYTES:
        fail("That file is over 10 MB.")
    raw = upload.read()
    upload.seek(0)
    scan = InvoiceScan(location=location, vendor=vendor, file=upload, created_by=user)
    read(scan, raw, content_type)
    scan.save()
    return scan


@transaction.atomic
def approve(scan: InvoiceScan, user) -> PurchaseOrder:
    if scan.status != InvoiceScan.Status.DRAFT:
        fail(f"{scan.number} is already {scan.get_status_display().lower()}.")
    if not scan.vendor:
        fail("Choose the vendor first.")
    items = {i.id: i for i in Item.objects.filter(id__in=[x.get("item") for x in scan.lines if x.get("item")])}
    lines, problems = [], []
    for n, x in enumerate(scan.lines, start=1):
        item, qty, price = items.get(x.get("item")), _num(x.get("qty")), _num(x.get("unit_price"))
        if not item:
            problems.append(f"line {n}: choose an item or remove the line")
        elif not qty or qty <= 0 or price is None or price < 0:
            problems.append(f"line {n} ({item.name}): enter quantity and unit price")
        elif item.vendor_id != scan.vendor_id:
            problems.append(f"line {n}: {item.name} isn't supplied by {scan.vendor.name}")
        else:
            lines.append((item, qty, price))
    if problems:
        fail("Fix these first: " + "; ".join(problems))
    if not lines:
        fail("There are no lines to book.")
    order = services.create_order(scan.vendor, scan.location, lines, user, source=PurchaseOrder.Source.INVOICE,
                                  note=f"From {scan.number}", on=scan.invoice_date or timezone.localdate())
    received = {line.id: (line.qty, line.unit_price) for line in order.lines.all()}
    changes = services.receive_order(order, received, user, scan.invoice_number, on=scan.invoice_date or timezone.localdate())
    scan.status, scan.order, scan.approved_by = InvoiceScan.Status.APPROVED, order, user
    scan.save(update_fields=["status", "order", "approved_by"])
    scan.price_changes = changes
    return order
