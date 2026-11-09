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

CSV_COLUMNS = ["date", "location", "pos_code", "qty", "net_sales"]


@transaction.atomic
def import_day(location, business_date: date, lines: list[tuple[MenuItem, int, Decimal]], user, source="CSV import") -> SalesDay:
    """Save one day's sales and book the theoretical usage (recipes × portions) as SALE movements.

    Importing the same location and date again replaces the earlier import, ledger entries included.
    """
    day, created = SalesDay.objects.get_or_create(location=location, business_date=business_date,
                                                  defaults={"source": source, "imported_by": user})
    if not created:
        Movement.objects.filter(location=location, kind=Movement.Kind.SALE, reference=day.reference).delete()
        day.lines.all().delete()
        day.source, day.imported_by = source, user
        day.save(update_fields=["source", "imported_by", "imported_at"])

    merged: dict[int, list] = {}
    for menu_item, qty, net in lines:
        if qty < 0:
            fail(f"{menu_item.name}: quantity can't be negative.")
        entry = merged.setdefault(menu_item.id, [menu_item, 0, ZERO])
        entry[1] += qty
        entry[2] += net
    SalesLine.objects.bulk_create(SalesLine(day=day, menu_item=m, qty=q, net_sales=n) for m, q, n in merged.values())

    usage: dict[int, list] = {}
    for menu_item, qty, _ in merged.values():
        for line in menu_item.lines.select_related("item"):
            entry = usage.setdefault(line.item_id, [line.item, ZERO])
            entry[1] += line.qty * qty
    for item, qty in usage.values():
        record(location, item, Movement.Kind.SALE, -qty, user, day.reference, business_date)
    return day


def parse_csv(raw: bytes) -> dict[tuple[str, date], list[tuple[str, int, Decimal]]]:
    """Read a POS export. Columns: date (YYYY-MM-DD), location (code), pos_code, qty, net_sales."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        fail("The file isn't UTF-8 text. Export it from your POS as CSV.")
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in CSV_COLUMNS if c not in header]
    if missing:
        fail(f"Missing columns: {', '.join(missing)}. Expected: {', '.join(CSV_COLUMNS)}.")
    groups = defaultdict(list)
    for n, row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        try:
            d = date.fromisoformat(row["date"])
            qty = int(Decimal(row["qty"]))
            net = Decimal(row["net_sales"] or "0")
        except (ValueError, InvalidOperation):
            fail(f"Row {n}: check the date (YYYY-MM-DD), qty and net_sales values.")
        groups[(row["location"].upper(), d)].append((row["pos_code"], qty, net))
    if not groups:
        fail("The file has no sales rows.")
    return groups


def import_csv(raw: bytes, user, allowed_location_ids: set[int]) -> list[SalesDay]:
    groups = parse_csv(raw)
    locations = {loc.code.upper(): loc for loc in Location.objects.all()}
    menu = {m.pos_code: m for m in MenuItem.objects.all()}
    unknown_loc = sorted({code for code, _ in groups if code not in locations})
    if unknown_loc:
        fail(f"Unknown location codes: {', '.join(unknown_loc)}.")
    unknown_items = sorted({code for rows in groups.values() for code, _, _ in rows if code not in menu})
    if unknown_items:
        fail(f"Unknown POS codes: {', '.join(unknown_items)}. Add them to the menu first.")
    for code, _ in groups:
        if locations[code].id not in allowed_location_ids:
            fail(f"You don't have access to location {code}.")
    days = []
    with transaction.atomic():
        for (code, d), rows in sorted(groups.items(), key=lambda kv: kv[0][1]):
            days.append(import_day(locations[code], d, [(menu[c], q, n) for c, q, n in rows], user))
    return days
