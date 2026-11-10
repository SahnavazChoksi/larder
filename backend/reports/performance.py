"""Outlet performance vs brand average: the weekly ops review sheet.

APC              average spend per cover = net sales ÷ covers
SSSG             same-store sales growth: this period vs the same weekdays a year earlier (364 days back)
Attach ratio     items of a category sold per cover (drinks, desserts)
SC removed %     bills where the service charge was taken off ÷ bills that had one
Complaints       logged complaints per 1,000 covers
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum

from catalog.models import Location
from sales.models import SalesDay, SalesLine

ATTACH = {"bev": "Drinks", "dessert": "Desserts"}
YEAR = timedelta(days=364)  # 52 weeks: keeps weekdays lined up


def _sales(ids, start, end):
    rows = SalesLine.objects.filter(day__location_id__in=ids, day__business_date__gte=start, day__business_date__lte=end) \
        .values("day__location").order_by().annotate(t=Sum("net_sales"))
    return defaultdict(Decimal, {r["day__location"]: r["t"] or Decimal(0) for r in rows})


def _days(ids, start, end):
    rows = SalesDay.objects.filter(location_id__in=ids, business_date__gte=start, business_date__lte=end) \
        .values("location").order_by().annotate(covers=Sum("covers"), bills=Sum("bills"),
                                                 sc_bills=Sum("sc_bills"), sc_removed=Sum("sc_removed"))
    return defaultdict(lambda: {"covers": 0, "bills": 0, "sc_bills": 0, "sc_removed": 0},
                       {r["location"]: {k: r[k] or 0 for k in ("covers", "bills", "sc_bills", "sc_removed")} for r in rows})


def _category_qty(ids, start, end):
    rows = SalesLine.objects.filter(day__location_id__in=ids, day__business_date__gte=start, day__business_date__lte=end,
                                    menu_item__category__in=ATTACH.values()) \
        .values("day__location", "menu_item__category").order_by().annotate(q=Sum("qty"))
    out = defaultdict(lambda: defaultdict(int))
    for r in rows:
        out[r["day__location"]][r["menu_item__category"]] = r["q"] or 0
    return out


def _complaints(ids, start, end):
    from ops.models import Complaint

    rows = Complaint.objects.filter(location_id__in=ids, occurred_on__gte=start, occurred_on__lte=end) \
        .values("location").order_by().annotate(n=Count("id"))
    return defaultdict(int, {r["location"]: r["n"] for r in rows})


def _div(a, b):
    return float(a) / float(b) if b else None


def _growth(now, before):
    return float(now) / float(before) - 1 if before else None


def _metrics(sales, days, cats, complaints, sales4_ly, salesq, salesq_ly):
    covers = days["covers"]
    return {
        "sales": float(sales), "covers": covers, "bills": days["bills"],
        "apc": _div(sales, covers), "avg_bill": _div(sales, days["bills"]),
        "sssg_4w": _growth(sales, sales4_ly), "sssg_qtr": _growth(salesq, salesq_ly),
        "bev_attach": _div(cats.get(ATTACH["bev"], 0), covers),
        "dessert_attach": _div(cats.get(ATTACH["dessert"], 0), covers),
        "sc_removed_pct": _div(days["sc_removed"], days["sc_bills"]),
        "sc_bills": days["sc_bills"], "sc_removed": days["sc_removed"],
        "complaints": complaints, "complaints_per_1000": _div(complaints * 1000, covers),
    }


def performance(user, end: date, location=None) -> dict:
    from ops.services import staffing

    outlets = list(Location.objects.filter(id__in=user.location_ids(), kind=Location.Kind.OUTLET))
    # Brand averages use every outlet of the brand, even ones this user can't open.
    brands = {o.brand for o in outlets}
    peers = list(Location.objects.filter(kind=Location.Kind.OUTLET, brand__in=brands))
    ids = [o.id for o in peers]

    s4, e4 = end - timedelta(days=27), end
    sq = end - timedelta(days=90)
    sales4, sales4_ly = _sales(ids, s4, e4), _sales(ids, s4 - YEAR, e4 - YEAR)
    salesq, salesq_ly = _sales(ids, sq, end), _sales(ids, sq - YEAR, end - YEAR)
    days, cats, comp = _days(ids, s4, e4), _category_qty(ids, s4, e4), _complaints(ids, s4, e4)

    rows = []
    for o in outlets:
        if location and o.id != location.id:
            continue
        m = _metrics(sales4[o.id], days[o.id], cats[o.id], comp[o.id], sales4_ly[o.id], salesq[o.id], salesq_ly[o.id])
        rows.append({"location": o.id, "name": o.name, "code": o.code, "brand": o.brand or "No brand", **m})

    brand_avg = {}
    for b in brands:
        group = [p for p in peers if p.brand == b]
        same_store = [p for p in group if sales4_ly[p.id] > 0]
        same_store_q = [p for p in group if salesq_ly[p.id] > 0]
        tot = {k: sum(days[p.id][k] for p in group) for k in ("covers", "bills", "sc_bills", "sc_removed")}
        tot_cats = defaultdict(int)
        for p in group:
            for k, v in cats[p.id].items():
                tot_cats[k] += v
        brand_avg[b or "No brand"] = _metrics(
            sum((sales4[p.id] for p in group), Decimal(0)), tot, tot_cats, sum(comp[p.id] for p in group),
            sum((sales4_ly[p.id] for p in same_store), Decimal(0)),
            sum((salesq[p.id] for p in same_store_q), Decimal(0)),
            sum((salesq_ly[p.id] for p in same_store_q), Decimal(0)),
        ) | {"outlets": len(group)}
        # growth must compare like with like: only stores that traded last year
        brand_avg[b or "No brand"]["sssg_4w"] = _growth(sum((sales4[p.id] for p in same_store), Decimal(0)),
                                                        sum((sales4_ly[p.id] for p in same_store), Decimal(0)))

    # 13-week trend, this year vs last year, for the outlets in view
    view_ids = [r["location"] for r in rows]
    trend = []
    week_end = end
    for _ in range(13):
        week_start = week_end - timedelta(days=6)
        now = sum(_sales(view_ids, week_start, week_end).values(), Decimal(0))
        ly = sum(_sales(view_ids, week_start - YEAR, week_end - YEAR).values(), Decimal(0))
        trend.append({"week_start": week_start, "this_year": float(now), "last_year": float(ly)})
        week_end = week_start - timedelta(days=1)
    trend.reverse()

    scope = [o for o in outlets if not location or o.id == location.id]
    return {
        "period": {"start": s4, "end": e4, "quarter_start": sq},
        "outlets": rows,
        "brand_avg": brand_avg,
        "trend": trend,
        "staffing": staffing(scope),
    }
