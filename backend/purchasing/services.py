from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Item, PriceHistory
from stock.models import Movement
from stock.services import ZERO, fail, on_hand_map, par_map, q4, record, round_up

from .models import PurchaseOrder, PurchaseOrderLine


@transaction.atomic
def create_order(vendor, location, lines, user, source=PurchaseOrder.Source.MANUAL, note="", on=None) -> PurchaseOrder:
    """lines: (item, qty, unit_price or None to use the item's last price)."""
    lines = [(i, q4(q), p) for i, q, p in lines if q4(q) > 0]
    if not lines:
        fail("Add at least one item with a quantity above zero.")
    wrong = [i.name for i, _, _ in lines if i.vendor_id != vendor.id]
    if wrong:
        fail(f"Not supplied by {vendor.name}: {', '.join(wrong)}.")
    on = on or timezone.localdate()
    order = PurchaseOrder.objects.create(
        vendor=vendor, location=location, source=source, note=note, created_on=on, created_by=user,
        expected_on=on + timedelta(days=vendor.lead_days),
    )
    PurchaseOrderLine.objects.bulk_create(
        PurchaseOrderLine(order=order, item=i, qty=q, unit_price=q4(p if p is not None else i.last_price))
        for i, q, p in lines
    )
    return order


def send_order(order: PurchaseOrder, on=None):
    if order.status != PurchaseOrder.Status.DRAFT:
        fail(f"{order.number} is already {order.get_status_display().lower()}.")
    order.status = PurchaseOrder.Status.SENT
    order.sent_on = on or timezone.localdate()
    order.save(update_fields=["status", "sent_on"])


@transaction.atomic
def receive_order(order: PurchaseOrder, received: dict[int, tuple[Decimal, Decimal | None]], user,
                  invoice_number="", on=None) -> list[str]:
    """Book a delivery. received: line id -> (qty, price or None for the ordered price).

    Adds stock, freezes the delivered price on the movement, updates the item's latest price and
    price history. Returns descriptions of price changes for the audit log.
    """
    if order.status not in (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.SENT):
        fail(f"{order.number} is {order.get_status_display().lower()} and can't be received.")
    on = on or timezone.localdate()
    changes = []
    for line in order.lines.select_related("item"):
        qty, price = received.get(line.id, (line.qty, None))
        qty, price = q4(qty), q4(price if price is not None else line.unit_price)
        if qty < 0 or price < 0:
            fail("Quantities and prices can't be negative.")
        line.qty_received, line.price_received = qty, price
        line.save(update_fields=["qty_received", "price_received"])
        item = line.item
        if qty > 0:
            record(order.location, item, Movement.Kind.PURCHASE, qty, user, order.number, on, price)
        if price != item.last_price:
            if item.last_price:
                change = (price / item.last_price) - 1
                changes.append(f"{item.name} ${item.last_price:.2f} → ${price:.2f} ({change:+.1%})")
            item.last_price = price
            item.save(update_fields=["last_price"])
        PriceHistory.objects.create(item=item, vendor=order.vendor, price=price, recorded_on=on, source=order.number)
    order.status = PurchaseOrder.Status.RECEIVED
    order.received_on, order.received_by, order.invoice_number = on, user, invoice_number
    order.save(update_fields=["status", "received_on", "received_by", "invoice_number"])
    return changes


def open_order_qty(location) -> dict[int, Decimal]:
    rows = (PurchaseOrderLine.objects
            .filter(order__location=location, order__status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.SENT])
            .values("item").order_by().annotate(q=Sum("qty")))
    return {r["item"]: r["q"] for r in rows}


def reorder_suggestions(location, cover=Decimal("1.5")) -> list[dict]:
    """Raw items below par, net of what's already on order. Orders up to `cover` × par."""
    stock, pars, on_order = on_hand_map(location), par_map(location), open_order_qty(location)
    items = Item.objects.filter(id__in=pars, kind=Item.Kind.RAW, is_active=True).select_related("vendor")
    rows = []
    for item in items:
        have = stock.get(item.id, ZERO) + on_order.get(item.id, ZERO)
        par = pars[item.id]
        if have >= par or not item.vendor:
            continue
        qty = round_up(par * cover - have, item.unit)
        rows.append({
            "item": item.id, "name": item.name, "unit": item.unit, "vendor": item.vendor_id,
            "vendor_name": item.vendor.name, "lead_days": item.vendor.lead_days,
            "on_hand": float(stock.get(item.id, ZERO)), "on_order": float(on_order.get(item.id, ZERO)),
            "par": float(par), "suggested": float(qty), "unit_price": float(item.last_price),
            "cost": float(qty * item.last_price),
        })
    rows.sort(key=lambda r: (r["vendor_name"], r["name"]))
    return rows


@transaction.atomic
def orders_from_suggestions(location, picks: list[tuple[Item, Decimal]], user, on=None) -> list[PurchaseOrder]:
    by_vendor = defaultdict(list)
    for item, qty in picks:
        if not item.vendor:
            fail(f"{item.name} has no vendor set.")
        by_vendor[item.vendor].append((item, qty, None))
    return [create_order(v, location, lines, user, PurchaseOrder.Source.REORDER, on=on) for v, lines in by_vendor.items()]


def recent_price_moves(days=14) -> list[dict]:
    """Items whose latest recorded price moved by the alert threshold or more vs the previous one."""
    since = timezone.localdate() - timedelta(days=days)
    out = []
    recent_items = PriceHistory.objects.filter(recorded_on__gte=since).values_list("item", flat=True).distinct()
    for item in Item.objects.filter(id__in=list(recent_items)).select_related("vendor"):
        hist = list(item.price_history.all()[:12])
        if len(hist) < 2:
            continue
        latest = hist[0].price
        previous = next((h.price for h in hist[1:] if h.price != latest), None)
        if not previous:
            continue
        change = latest / previous - 1
        if abs(change) >= settings.PRICE_ALERT_THRESHOLD:
            out.append({"item": item.id, "name": item.name, "unit": item.unit, "vendor": item.vendor.name if item.vendor else "",
                        "previous": float(previous), "latest": float(latest), "change": float(change),
                        "on": hist[0].recorded_on})
    return out
