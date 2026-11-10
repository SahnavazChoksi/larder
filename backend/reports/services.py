"""Read-only reporting over the stock ledger and sales.

Theoretical usage  = SALE movements (recipes × portions the POS sold)
Actual usage       = theoretical + logged wastage + count losses
Unexplained        = count losses (stock that vanished without a record)
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from catalog.models import Item, Location
from sales.models import SalesLine
from stock.models import Movement, Transfer
from stock.services import ZERO, on_hand_map, par_map, stock_status

VALUE = ExpressionWrapper(F("qty") * F("unit_cost"), output_field=DecimalField(max_digits=24, decimal_places=8))
K = Movement.Kind


def _sums(location, start=None, end=None, before=None):
    qs = Movement.objects.filter(location=location)
    if before:
        qs = qs.filter(occurred_on__lt=before)
    if start:
        qs = qs.filter(occurred_on__gte=start)
    if end:
        qs = qs.filter(occurred_on__lte=end)
    return qs


def revenue(location, start, end) -> Decimal:
    return SalesLine.objects.filter(
        day__location=location, day__business_date__gte=start, day__business_date__lte=end
    ).aggregate(t=Sum("net_sales"))["t"] or ZERO


def variance(location: Location, start: date, end: date) -> dict:
    by_item = defaultdict(lambda: defaultdict(lambda: [ZERO, ZERO]))  # item -> kind -> [qty, value]
    rows = _sums(location, start, end).values("item", "kind").order_by().annotate(q=Sum("qty"), v=Sum(VALUE))
    totals = defaultdict(lambda: ZERO)
    for r in rows:
        by_item[r["item"]][r["kind"]] = [r["q"] or ZERO, r["v"] or ZERO]
        totals[r["kind"]] += r["v"] or ZERO

    opening = _sums(location, before=start).aggregate(v=Sum(VALUE))["v"] or ZERO
    closing = _sums(location, end=end).aggregate(v=Sum(VALUE))["v"] or ZERO

    items = {i.id: i for i in Item.objects.filter(id__in=by_item)}
    out_rows = []
    for item_id, kinds in by_item.items():
        theo_q, theo_v = -kinds[K.SALE.value][0], -kinds[K.SALE.value][1]
        waste_q, waste_v = -kinds[K.WASTAGE.value][0], -kinds[K.WASTAGE.value][1]
        loss_q, loss_v = -kinds[K.COUNT.value][0], -kinds[K.COUNT.value][1]
        if not (theo_q or waste_q or loss_q):
            continue
        item = items[item_id]
        actual_q = theo_q + waste_q + loss_q
        out_rows.append({
            "item": item_id, "name": item.name, "unit": item.unit, "category": item.category,
            "theoretical_qty": float(theo_q), "actual_qty": float(actual_q),
            "wastage_qty": float(waste_q), "unexplained_qty": float(loss_q),
            "theoretical_value": float(theo_v), "actual_value": float(theo_v + waste_v + loss_v),
            "wastage_value": float(waste_v), "unexplained_value": float(loss_v),
            "unexplained_pct": float(loss_q / theo_q) if theo_q > 0 else None,
        })
    out_rows.sort(key=lambda r: -r["unexplained_value"])

    theo = -totals[K.SALE.value]
    actual = theo - totals[K.WASTAGE.value] - totals[K.COUNT.value]
    rev = revenue(location, start, end)
    return {
        "location": location.id, "location_name": location.name, "start": start, "end": end,
        "summary": {
            "opening_value": float(opening),
            "purchases": float(totals[K.PURCHASE.value] + totals[K.OPENING.value]),
            "transfers_in": float(totals[K.TRANSFER_IN.value]),
            "transfers_out": float(-totals[K.TRANSFER_OUT.value]),
            "production_net": float(totals[K.PRODUCTION_IN.value] + totals[K.PRODUCTION_OUT.value]),
            "closing_value": float(closing),
            "theoretical_cost": float(theo),
            "wastage": float(-totals[K.WASTAGE.value]),
            "unexplained": float(-totals[K.COUNT.value]),
            "actual_cost": float(actual),
            "revenue": float(rev),
            "theoretical_pct": float(theo / rev) if rev else None,
            "actual_pct": float(actual / rev) if rev else None,
            "target_pct": float(settings.FOOD_COST_TARGET),
        },
        "items": out_rows,
    }


def daily_revenue(locations, start, end) -> list[dict]:
    rows = SalesLine.objects.filter(
        day__location__in=locations, day__business_date__gte=start, day__business_date__lte=end
    ).values("day__business_date").order_by().annotate(t=Sum("net_sales"))
    found = {r["day__business_date"]: r["t"] for r in rows}
    out, d = [], start
    while d <= end:
        out.append({"date": d, "revenue": float(found.get(d, ZERO))})
        d += timedelta(days=1)
    return out


def dashboard(user, start: date, end: date, location: Location | None = None) -> dict:
    from purchasing.models import PurchaseOrder
    from purchasing.services import recent_price_moves

    allowed = Location.objects.filter(id__in=user.location_ids())
    scope = [location] if location else list(allowed)
    outlets = [loc for loc in scope if loc.kind == Location.Kind.OUTLET]
    target = settings.FOOD_COST_TARGET

    scorecard, losses, alerts = [], defaultdict(lambda: {"name": "", "value": 0.0}), []
    for loc in scope:
        v = variance(loc, start, end)
        s = v["summary"]
        scorecard.append({"location": loc.id, "name": loc.name, "kind": loc.kind, **s})
        for r in v["items"]:
            losses[r["item"]]["name"] = r["name"]
            losses[r["item"]]["value"] += r["unexplained_value"]
        if s["actual_pct"] is not None and s["actual_pct"] > float(target) + 0.01:
            alerts.append({"severity": "warn", "title": f"{loc.name} food cost {s['actual_pct']:.1%} vs {target:.0%} target",
                           "detail": f"Recipes say {s['theoretical_pct']:.1%}. The gap is ${s['actual_cost'] - s['theoretical_cost']:,.0f}.",
                           "link": f"/variance?location={loc.id}"})
        worst = next((r for r in v["items"] if (r["unexplained_pct"] or 0) > 0.08 and r["unexplained_value"] > 100), None)
        if worst:
            alerts.append({"severity": "bad",
                           "title": f"{worst['name']} at {loc.name}: {worst['unexplained_pct']:.0%} more used than recipes allow",
                           "detail": f"${worst['unexplained_value']:,.0f} unexplained. Check portioning and receiving.",
                           "link": f"/variance?location={loc.id}"})
        stock, pars = on_hand_map(loc), par_map(loc)
        low = [i for i, p in pars.items() if stock_status(stock.get(i, ZERO), p) in ("low", "out")]
        if low:
            names = list(Item.objects.filter(id__in=low[:4]).values_list("name", flat=True))
            alerts.append({"severity": "bad", "title": f"{len(low)} item{'s' if len(low) > 1 else ''} low or out at {loc.name}",
                           "detail": ", ".join(names) + ("…" if len(low) > 4 else ""), "link": f"/stock?location={loc.id}"})

    for move in recent_price_moves():
        up = move["change"] > 0
        alerts.append({"severity": "warn" if up else "info",
                       "title": f"{move['name']} {'up' if up else 'down'} {abs(move['change']):.1%} at {move['vendor']}",
                       "detail": f"Now ${move['latest']:.2f}/{move['unit']} (was ${move['previous']:.2f}). Recipe costs updated.",
                       "link": "/recipes"})

    ids = [loc.id for loc in scope]
    short = Transfer.objects.filter(to_location_id__in=ids, status=Transfer.Status.RECEIVED,
                                    received_on__gte=start, received_on__lte=end).prefetch_related("lines__item")
    for t in short:
        bad = [line for line in t.lines.all() if line.qty_received is not None and line.qty_received < line.qty_sent]
        if bad:
            alerts.append({"severity": "warn", "title": f"{t.number} arrived short at {t.to_location.name}",
                           "detail": "; ".join(f"{line.item.name}: sent {line.qty_sent:.2f}, received {line.qty_received:.2f}"
                                               for line in bad), "link": "/transfers"})

    today = timezone.localdate()
    late = PurchaseOrder.objects.filter(location_id__in=ids, status=PurchaseOrder.Status.SENT, expected_on__lt=today)
    for po in late.select_related("vendor", "location"):
        alerts.append({"severity": "warn", "title": f"{po.number} from {po.vendor.name} is late",
                       "detail": f"Expected {po.expected_on:%b %d} at {po.location.name}.", "link": "/purchasing"})

    from checklists.services import alerts as checklist_alerts, compliance

    alerts.extend(checklist_alerts(scope))
    checks = compliance(scope, end - timedelta(days=6), end)

    order = {"bad": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: order[a["severity"]])

    sales_total = sum(s["revenue"] for s in scorecard)
    theo_total = sum(s["theoretical_cost"] for s in scorecard if s["kind"] == Location.Kind.OUTLET)
    actual_total = sum(s["actual_cost"] for s in scorecard if s["kind"] == Location.Kind.OUTLET)
    return {
        "start": start, "end": end,
        "totals": {
            "revenue": sales_total,
            "theoretical_pct": theo_total / sales_total if sales_total else None,
            "actual_pct": actual_total / sales_total if sales_total else None,
            "unexplained": sum(s["unexplained"] for s in scorecard),
            "wastage": sum(s["wastage"] for s in scorecard),
            "stock_value": sum(s["closing_value"] for s in scorecard),
            "target_pct": float(target),
        },
        "daily_revenue": daily_revenue(outlets, start, end) if outlets else [],
        "scorecard": scorecard,
        "top_losses": sorted(({"item": k, **v} for k, v in losses.items() if v["value"] > 0),
                             key=lambda r: -r["value"])[:8],
        "alerts": alerts,
        "checklists": checks["locations"],
    }
