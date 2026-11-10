import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from catalog.models import Location, MenuItem
from stock.models import Movement
from stock.services import ZERO, fail, record

from .models import SalesDay, SalesLine

ITEM_COLUMNS = ["date", "location", "pos_code", "qty", "net_sales"]
SUMMARY_COLUMNS = ["date", "location", "covers", "bills"]
# optional: service_charge_bills, service_charge_removed, tickets, avg_prep_minutes, loyalty_bills
TOTAL_FIELDS = ("covers", "bills", "sc_bills", "sc_removed", "tickets", "loyalty_bills")


def _clear_usage(day: SalesDay):
    Movement.objects.filter(location=day.location, kind=Movement.Kind.SALE, reference=day.reference).delete()


@transaction.atomic
def import_day(location, business_date: date, lines: list[tuple[MenuItem, int, Decimal]], user,
               source="CSV import", totals: dict | None = None, history=False) -> SalesDay:
    """Save one day's item sales and book theoretical usage (recipes × portions) as SALE movements.

    Re-importing the same location and date replaces the earlier lines and usage.
    history=True stores sales for trends (e.g. last year's figures) without touching stock.
    totals: optional covers / bills / sc_bills / sc_removed for the day.
    """
    day, created = SalesDay.objects.get_or_create(location=location, business_date=business_date,
                                                  defaults={"source": source, "imported_by": user, "is_history": history})
    if not created:
        _clear_usage(day)
        day.lines.all().delete()
        day.source, day.imported_by, day.is_history = source, user, history
    _apply_totals(day, totals or {})
    day.save()

    merged: dict[int, list] = {}
    for menu_item, qty, net in lines:
        if qty < 0:
            fail(f"{menu_item.name}: quantity can't be negative.")
        entry = merged.setdefault(menu_item.id, [menu_item, 0, ZERO])
        entry[1] += qty
        entry[2] += net
    SalesLine.objects.bulk_create(SalesLine(day=day, menu_item=m, qty=q, net_sales=n) for m, q, n in merged.values())
    if history:
        return day

    usage: dict[int, list] = {}
    for menu_item, qty, _ in merged.values():
        for line in menu_item.lines.select_related("item"):
            entry = usage.setdefault(line.item_id, [line.item, ZERO])
            entry[1] += line.qty * qty
    for item, qty in usage.values():
        record(location, item, Movement.Kind.SALE, -qty, user, day.reference, business_date)
    return day


def _apply_totals(day, totals: dict):
    for field in TOTAL_FIELDS:
        if totals.get(field) is not None:
            setattr(day, field, max(0, int(totals[field])))
    if totals.get("prep_minutes") is not None:
        day.prep_minutes = max(Decimal(0), Decimal(str(totals["prep_minutes"]))).quantize(Decimal("0.1"))


def set_day_totals(location, business_date: date, totals: dict, user, source="CSV import") -> SalesDay:
    """Covers, bills and service-charge counts for a day (from the POS daily summary)."""
    day, _ = SalesDay.objects.get_or_create(location=location, business_date=business_date,
                                            defaults={"source": source, "imported_by": user})
    _apply_totals(day, totals)
    if day.sc_removed > day.sc_bills:
        fail(f"{location.code} {business_date}: service charge removed on more bills than had one.")
    day.save()
    return day


def _read(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        fail("The file isn't UTF-8 text. Export it from your POS as CSV.")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    return reader, header


def _rows(reader):
    for n, row in enumerate(reader, start=2):
        yield n, {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}


def parse_items(reader):
    groups = defaultdict(list)
    for n, row in _rows(reader):
        try:
            d = date.fromisoformat(row["date"])
            qty = int(Decimal(row["qty"]))
            net = Decimal(row["net_sales"] or "0")
        except (ValueError, InvalidOperation):
            fail(f"Row {n}: check the date (YYYY-MM-DD), qty and net_sales values.")
        groups[(row["location"].upper(), d)].append((row["pos_code"], qty, net))
    return groups


def parse_summary(reader):
    out = {}
    for n, row in _rows(reader):
        try:
            d = date.fromisoformat(row["date"])
            totals = {
                "covers": int(row["covers"] or 0), "bills": int(row["bills"] or 0),
                "sc_bills": int(row.get("service_charge_bills") or 0),
                "sc_removed": int(row.get("service_charge_removed") or 0),
                "loyalty_bills": int(row.get("loyalty_bills") or 0),
            }
            tickets = int(row.get("tickets") or 0)
            avg = Decimal(row.get("avg_prep_minutes") or "0")
            totals |= {"tickets": tickets, "prep_minutes": avg * tickets}
        except (ValueError, InvalidOperation):
            fail(f"Row {n}: dates must be YYYY-MM-DD and counts whole numbers.")
        out[(row["location"].upper(), d)] = totals
    return out


def import_csv(raw: bytes, user, allowed_location_ids: set[int], history=False) -> tuple[str, int]:
    """Two formats, told apart by their header:
    item sales:   date, location, pos_code, qty, net_sales
    day summary:  date, location, covers, bills [, service_charge_bills, service_charge_removed]
    """
    reader, header = _read(raw)
    if all(c in header for c in ITEM_COLUMNS):
        kind, groups = "items", parse_items(reader)
    elif all(c in header for c in SUMMARY_COLUMNS):
        kind, groups = "summary", parse_summary(reader)
    else:
        fail("Unrecognised columns. Item sales need: " + ", ".join(ITEM_COLUMNS)
             + ". A daily summary needs: " + ", ".join(SUMMARY_COLUMNS)
             + " (plus optional service_charge_bills, service_charge_removed, tickets, avg_prep_minutes, loyalty_bills).")
    if not groups:
        fail("The file has no rows.")
    locations = {loc.code.upper(): loc for loc in Location.objects.all()}
    unknown_loc = sorted({code for code, _ in groups if code not in locations})
    if unknown_loc:
        fail(f"Unknown location codes: {', '.join(unknown_loc)}.")
    for code, _ in groups:
        if locations[code].id not in allowed_location_ids:
            fail(f"You don't have access to location {code}.")
    with transaction.atomic():
        if kind == "summary":
            for (code, d), totals in groups.items():
                set_day_totals(locations[code], d, totals, user)
            return kind, len(groups)
        menu = {m.pos_code: m for m in MenuItem.objects.all()}
        unknown_items = sorted({code for rows in groups.values() for code, _, _ in rows if code not in menu})
        if unknown_items:
            fail(f"Unknown POS codes: {', '.join(unknown_items)}. Add them to the menu first.")
        for (code, d), rows in sorted(groups.items(), key=lambda kv: kv[0][1]):
            import_day(locations[code], d, [(menu[c], q, n) for c, q, n in rows], user,
                       source="History import" if history else "CSV import", history=history)
    return kind, len(groups)
