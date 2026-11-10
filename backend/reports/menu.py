"""Menu engineering and sales forecasting."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from catalog.models import Item, MenuItem
from purchasing.services import open_order_qty
from sales.models import SalesLine
from stock.services import ZERO, on_hand_map, round_up

CLASSES = {
    "star": ("Star", "Popular and profitable. Keep it prominent; protect the recipe and portion."),
    "plowhorse": ("Plowhorse", "Popular, thin margin. Trim plate cost or nudge the price up."),
    "puzzle": ("Puzzle", "Good margin, few orders. Move it up the menu; train staff to suggest it."),
    "dog": ("Dog", "Low on both. Rework, reprice or remove it."),
}


def menu_engineering(location_ids, start: date, end: date, category: str | None = None) -> dict:
    """Kasavana–Smith: popularity vs the 70% rule, contribution margin vs the weighted average."""
    qs = SalesLine.objects.filter(day__location_id__in=location_ids, day__business_date__gte=start, day__business_date__lte=end)
    if category:
        qs = qs.filter(menu_item__category=category)
    sold = {r["menu_item"]: (r["q"] or 0, r["n"] or ZERO) for r in qs.values("menu_item").order_by().annotate(q=Sum("qty"), n=Sum("net_sales"))}
    dishes = MenuItem.objects.filter(is_active=True)
    if category:
        dishes = dishes.filter(category=category)
    rows = []
    for d in dishes:
        qty, revenue = sold.get(d.id, (0, ZERO))
        cost = d.plate_cost()
        avg_price = revenue / qty if qty else d.price
        rows.append({"id": d.id, "name": d.name, "category": d.category, "qty": qty, "price": float(avg_price),
                     "cost": float(cost), "margin": float(avg_price - cost), "food_cost_pct": float(cost / avg_price) if avg_price else None})
    total = sum(r["qty"] for r in rows)
    if not rows or not total:
        return {"rows": rows, "popularity_threshold": None, "average_margin": None, "classes": CLASSES}
    threshold = 0.7 / len(rows)
    avg_margin = sum(r["qty"] * r["margin"] for r in rows) / total
    for r in rows:
        r["mix"] = r["qty"] / total
        r["total_margin"] = r["qty"] * r["margin"]
        popular, profitable = r["mix"] >= threshold, r["margin"] >= avg_margin
        r["class"] = "star" if popular and profitable else "plowhorse" if popular else "puzzle" if profitable else "dog"
    rows.sort(key=lambda r: -r["total_margin"])
    return {"rows": rows, "popularity_threshold": threshold * total, "average_margin": avg_margin, "classes": CLASSES}


def forecast(location, today: date, days=7, history_weeks=4) -> dict:
    """Portions per dish for the next `days`: same-weekday average of recent weeks × recent trend."""
    start = today - timedelta(days=history_weeks * 7)
    rows = SalesLine.objects.filter(day__location=location, day__business_date__gte=start, day__business_date__lt=today) \
        .values("menu_item", "day__business_date").order_by().annotate(q=Sum("qty"))
    by_dish_day = defaultdict(dict)
    for r in rows:
        by_dish_day[r["menu_item"]][r["day__business_date"]] = r["q"]
    recent = sum(q for d in by_dish_day.values() for day, q in d.items() if day >= today - timedelta(days=14))
    earlier = sum(q for d in by_dish_day.values() for day, q in d.items() if day < today - timedelta(days=14))
    trend = min(1.1, max(0.9, recent / earlier)) if earlier else 1.0

    dates = [today + timedelta(days=k) for k in range(days)]
    dishes = list(MenuItem.objects.filter(is_active=True))
    out = []
    for d in dishes:
        history = by_dish_day.get(d.id, {})
        per_day = []
        for day in dates:
            same = [history.get(day - timedelta(weeks=w), 0) for w in range(1, history_weeks + 1)]
            per_day.append(round(sum(same) / len(same) * trend))
        out.append({"id": d.id, "name": d.name, "category": d.category, "price": float(d.price), "days": per_day, "total": sum(per_day)})
    return {"dates": dates, "trend": trend, "dishes": out,
            "totals": [sum(r["days"][i] for r in out) for i in range(days)],
            "revenue": [sum(r["days"][i] * r["price"] for r in out) for i in range(days)]}


def smart_reorder(location, today: date) -> list[dict]:
    """Raw items the forecast will run short of before the vendor's next delivery (+2 days of cover)."""
    fc = forecast(location, today)
    dishes = {d.id: d for d in MenuItem.objects.prefetch_related("lines__item")}
    stock, on_order = on_hand_map(location), open_order_qty(location)
    need = defaultdict(lambda: ZERO)
    items = {}
    for row in fc["dishes"]:
        for line in dishes[row["id"]].lines.all():
            if line.item.kind != Item.Kind.RAW or not line.item.vendor_id:
                continue
            items[line.item_id] = line.item
            horizon = min(len(row["days"]), line.item.vendor.lead_days + 2)
            need[line.item_id] += line.qty * sum(row["days"][:horizon])
    out = []
    for item_id, qty in need.items():
        item = items[item_id]
        have = stock.get(item_id, ZERO) + on_order.get(item_id, ZERO)
        short = qty * Decimal("1.05") - have  # 5% buffer for normal loss
        if short > 0:
            order = round_up(short, item.unit)
            out.append({"item": item_id, "name": item.name, "unit": item.unit, "vendor": item.vendor_id,
                        "vendor_name": item.vendor.name, "lead_days": item.vendor.lead_days,
                        "need": float(qty), "on_hand": float(stock.get(item_id, ZERO)),
                        "on_order": float(on_order.get(item_id, ZERO)), "suggested": float(order),
                        "unit_price": float(item.last_price), "cost": float(order * item.last_price)})
    out.sort(key=lambda r: (r["vendor_name"], r["name"]))
    return out
