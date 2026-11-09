"""Every change to stock goes through these functions so the ledger stays consistent.

Views call them, the seed command calls them, and tests can call them directly.
"""
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Item, Location

from .models import Movement, ParLevel, ProductionBatch, StockCount, StockCountLine, Transfer, TransferLine, Wastage

ZERO = Decimal("0")
Q4 = Decimal("0.0001")


def q4(value) -> Decimal:
    return Decimal(str(value)).quantize(Q4, rounding=ROUND_HALF_UP)


def fail(message: str):
    raise ValidationError({"detail": message})


def fmt_qty(qty, unit) -> str:
    qty = Decimal(qty)
    if unit == "pc":
        return f"{qty.quantize(Decimal('1'))} {unit}"
    return f"{qty.quantize(Decimal('0.01')).normalize():f} {unit}"


def round_up(qty: Decimal, unit: str) -> Decimal:
    """Round an order quantity up to something a person would order: whole pieces, half kg/L."""
    if unit == "pc":
        return qty.quantize(Decimal("1"), rounding=ROUND_CEILING)
    return (qty * 2).quantize(Decimal("1"), rounding=ROUND_CEILING) / 2


# ---------- reading ----------

def on_hand_map(location: Location, as_of: date | None = None) -> dict[int, Decimal]:
    qs = Movement.objects.filter(location=location)
    if as_of:
        qs = qs.filter(occurred_on__lte=as_of)
    rows = qs.values("item").order_by().annotate(total=Sum("qty"))
    return {r["item"]: r["total"] or ZERO for r in rows}


def on_hand(location: Location, item: Item) -> Decimal:
    return Movement.objects.filter(location=location, item=item).aggregate(t=Sum("qty"))["t"] or ZERO


def par_map(location: Location) -> dict[int, Decimal]:
    return {p.item_id: p.par for p in ParLevel.objects.filter(location=location)}


def stock_status(qty: Decimal, par: Decimal | None) -> str:
    if par is None:
        return "no_par"
    if qty <= 0:
        return "out"
    if qty < par / 2:
        return "low"
    if qty < par:
        return "below_par"
    if qty > par * Decimal("1.8"):
        return "over"
    return "ok"


def stock_levels(location: Location) -> list[dict]:
    """One row per item the location stocks or has a par for."""
    today = timezone.localdate()
    stock = on_hand_map(location)
    pars = par_map(location)
    last_in = {
        r["item"]: r["d"]
        for r in Movement.objects.filter(location=location, qty__gt=0).values("item").order_by().annotate(d=Max("occurred_on"))
    }
    rows = []
    for item in Item.objects.filter(id__in=set(stock) | set(pars)).select_related("vendor"):
        qty = stock.get(item.id, ZERO)
        par = pars.get(item.id)
        cost = item.unit_cost()
        days_left = None
        if item.shelf_life_days and item.shelf_life_days <= 60 and item.id in last_in and qty > 0:
            days_left = item.shelf_life_days - (today - last_in[item.id]).days
        rows.append({
            "item": item.id, "name": item.name, "category": item.category, "kind": item.kind, "unit": item.unit,
            "vendor": item.vendor.name if item.vendor else None,
            "on_hand": float(qty), "par": float(par) if par is not None else None,
            "status": stock_status(qty, par), "unit_cost": float(cost), "value": float(qty * cost),
            "days_left": days_left,
        })
    rows.sort(key=lambda r: (r["category"], r["name"]))
    return rows


# ---------- writing ----------

def record(location, item, kind, qty, user=None, reference="", occurred_on=None, unit_cost=None) -> Movement | None:
    qty = q4(qty)
    if qty == 0:
        return None
    cost = item.unit_cost() if unit_cost is None else unit_cost
    return Movement.objects.create(
        location=location, item=item, kind=kind, qty=qty, unit_cost=q4(cost),
        occurred_on=occurred_on or timezone.localdate(), reference=reference[:60], created_by=user,
    )


@transaction.atomic
def set_pars(location, pars: list[tuple[Item, Decimal | None]], user) -> list[str]:
    """pars: (item, new_par or None to remove). Returns human-readable changes for the audit log."""
    current = {p.item_id: p for p in ParLevel.objects.filter(location=location)}
    changes = []
    for item, new in pars:
        existing = current.get(item.id)
        if new is None:
            if existing:
                changes.append(f"{item.name} {fmt_qty(existing.par, item.unit)} → removed")
                existing.delete()
            continue
        if new < 0:
            fail(f"{item.name}: par can't be negative.")
        if existing and existing.par == new:
            continue
        old = fmt_qty(existing.par, item.unit) if existing else "none"
        ParLevel.objects.update_or_create(location=location, item=item, defaults={"par": new, "updated_by": user})
        changes.append(f"{item.name} {old} → {fmt_qty(new, item.unit)}")
    return changes


@transaction.atomic
def post_count(location, lines: list[tuple[Item, Decimal]], user, counted_on=None, note="") -> StockCount:
    """Record a physical count. The difference to the system figure becomes a COUNT movement:
    that difference is the 'unexplained' variance in reports."""
    if not lines:
        fail("Enter at least one counted item.")
    counted_on = counted_on or timezone.localdate()
    current = on_hand_map(location, as_of=counted_on)
    count = StockCount.objects.create(location=location, counted_on=counted_on, note=note, created_by=user)
    total = ZERO
    for item, counted in lines:
        counted = q4(counted)
        if counted < 0:
            fail(f"{item.name}: a count can't be negative.")
        system = q4(current.get(item.id, ZERO))
        StockCountLine.objects.create(count=count, item=item, system_qty=system, counted_qty=counted)
        movement = record(location, item, Movement.Kind.COUNT, counted - system, user, count.number, counted_on)
        if movement:
            total += movement.value
    count.value_difference = total.quantize(Decimal("0.01"))
    count.save(update_fields=["value_difference"])
    return count


@transaction.atomic
def log_wastage(location, item, qty, reason, user, note="", occurred_on=None) -> Wastage:
    qty = q4(qty)
    if qty <= 0:
        fail("Wastage quantity must be above zero.")
    occurred_on = occurred_on or timezone.localdate()
    cost = item.unit_cost()
    entry = Wastage.objects.create(
        location=location, item=item, qty=qty, unit_cost=q4(cost), reason=reason, note=note,
        occurred_on=occurred_on, created_by=user,
    )
    record(location, item, Movement.Kind.WASTAGE, -qty, user, f"WASTE-{entry.id}", occurred_on, cost)
    return entry


@transaction.atomic
def request_transfer(from_location, to_location, lines: list[tuple[Item, Decimal]], user, note="", on=None) -> Transfer:
    if from_location == to_location:
        fail("Pick two different locations.")
    lines = [(item, q4(qty)) for item, qty in lines if q4(qty) > 0]
    if not lines:
        fail("Add at least one item with a quantity above zero.")
    transfer = Transfer.objects.create(
        from_location=from_location, to_location=to_location, note=note,
        requested_by=user, requested_on=on or timezone.localdate(),
    )
    TransferLine.objects.bulk_create(TransferLine(transfer=transfer, item=i, qty_requested=q) for i, q in lines)
    return transfer


@transaction.atomic
def dispatch_transfer(transfer: Transfer, sent: dict[int, Decimal], user, on=None) -> Transfer:
    """sent: line id -> quantity actually sent (defaults to the requested quantity)."""
    if transfer.status != Transfer.Status.REQUESTED:
        fail(f"{transfer.number} has already been {transfer.get_status_display().lower()}.")
    on = on or timezone.localdate()
    stock = on_hand_map(transfer.from_location)
    problems = []
    lines = list(transfer.lines.select_related("item"))
    for line in lines:
        qty = q4(sent.get(line.id, line.qty_requested))
        if qty < 0:
            fail("Sent quantities can't be negative.")
        if qty > stock.get(line.item_id, ZERO):
            have = stock.get(line.item_id, ZERO)
            problems.append(f"{line.item.name} (sending {fmt_qty(qty, line.item.unit)}, have {fmt_qty(have, line.item.unit)})")
        line.qty_sent = qty
    if problems:
        fail(f"Not enough stock at {transfer.from_location.name}: " + "; ".join(problems))
    for line in lines:
        cost = line.item.unit_cost()
        line.unit_cost = q4(cost)
        line.save(update_fields=["qty_sent", "unit_cost"])
        record(transfer.from_location, line.item, Movement.Kind.TRANSFER_OUT, -line.qty_sent, user, transfer.number, on, cost)
    transfer.status = Transfer.Status.DISPATCHED
    transfer.dispatched_by, transfer.dispatched_on = user, on
    transfer.save(update_fields=["status", "dispatched_by", "dispatched_on"])
    return transfer


@transaction.atomic
def receive_transfer(transfer: Transfer, received: dict[int, Decimal], user, on=None) -> list[str]:
    """Book what actually arrived. Returns descriptions of short lines (sent − received)."""
    if transfer.status != Transfer.Status.DISPATCHED:
        fail(f"{transfer.number} can't be received: it is {transfer.get_status_display().lower()}.")
    on = on or timezone.localdate()
    short = []
    for line in transfer.lines.select_related("item"):
        qty = q4(received.get(line.id, line.qty_sent))
        if qty < 0:
            fail("Received quantities can't be negative.")
        line.qty_received = qty
        line.save(update_fields=["qty_received"])
        record(transfer.to_location, line.item, Movement.Kind.TRANSFER_IN, qty, user, transfer.number, on, line.unit_cost)
        if qty < line.qty_sent:
            short.append(f"{line.item.name} short {fmt_qty(line.qty_sent - qty, line.item.unit)}")
    transfer.status = Transfer.Status.RECEIVED
    transfer.received_by, transfer.received_on = user, on
    transfer.save(update_fields=["status", "received_by", "received_on"])
    return short


def batch_requirements(batch: ProductionBatch) -> list[tuple[Item, Decimal]]:
    return [(line.component, line.qty * batch.qty) for line in batch.item.recipe_lines.select_related("component")]


@transaction.atomic
def complete_batch(batch: ProductionBatch, user, on=None) -> ProductionBatch:
    """Cook a batch: take the ingredients out of the kitchen's stock and add the prep."""
    if batch.status != ProductionBatch.Status.PLANNED:
        fail(f"{batch.number} is already cooked.")
    on = on or timezone.localdate()
    needs = batch_requirements(batch)
    if not needs:
        fail(f"{batch.item.name} has no recipe yet. Add one under Recipes first.")
    stock = on_hand_map(batch.location)
    short = [
        f"{item.name} (need {fmt_qty(qty, item.unit)}, have {fmt_qty(stock.get(item.id, ZERO), item.unit)})"
        for item, qty in needs if stock.get(item.id, ZERO) < qty
    ]
    if short:
        fail("Not enough stock to cook this batch: " + "; ".join(short))
    total = ZERO
    for item, qty in needs:
        cost = item.unit_cost()
        total += qty * cost
        record(batch.location, item, Movement.Kind.PRODUCTION_OUT, -qty, user, batch.number, on, cost)
    record(batch.location, batch.item, Movement.Kind.PRODUCTION_IN, batch.qty, user, batch.number, on, total / batch.qty)
    batch.status = ProductionBatch.Status.DONE
    batch.completed_on, batch.completed_by = on, user
    batch.save(update_fields=["status", "completed_on", "completed_by"])
    return batch


def prep_demand(kitchen: Location) -> list[dict]:
    """For each prep: what outlets are short of par, what's requested, what the kitchen holds and has planned."""
    preps = Item.objects.filter(kind=Item.Kind.PREP, is_active=True)
    outlets = Location.objects.filter(kind=Location.Kind.OUTLET)
    outlet_short = {p.id: ZERO for p in preps}
    for outlet in outlets:
        stock, pars = on_hand_map(outlet), par_map(outlet)
        for p in preps:
            if p.id in pars:
                outlet_short[p.id] += max(ZERO, pars[p.id] - stock.get(p.id, ZERO))
    requested = {
        r["item"]: r["q"] for r in TransferLine.objects.filter(
            transfer__from_location=kitchen, transfer__status=Transfer.Status.REQUESTED
        ).values("item").order_by().annotate(q=Sum("qty_requested"))
    }
    planned = {
        r["item"]: r["q"] for r in ProductionBatch.objects.filter(
            location=kitchen, status=ProductionBatch.Status.PLANNED
        ).values("item").order_by().annotate(q=Sum("qty"))
    }
    kitchen_stock = on_hand_map(kitchen)
    rows = []
    for p in preps:
        need = max(outlet_short[p.id], requested.get(p.id, ZERO))
        gap = need - kitchen_stock.get(p.id, ZERO) - planned.get(p.id, ZERO)
        rows.append({
            "item": p.id, "name": p.name, "unit": p.unit, "batch_size": float(p.batch_size or 0),
            "outlets_short": float(outlet_short[p.id]), "requested": float(requested.get(p.id, ZERO)),
            "in_kitchen": float(kitchen_stock.get(p.id, ZERO)), "planned": float(planned.get(p.id, ZERO)),
            "to_make": float(round_up(gap, p.unit)) if gap > 0 else 0.0,
        })
    return rows
