"""Scheduling, time clock and labour reporting (cost, labour %, sales per labour hour, tip pool)."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from sales.models import SalesLine
from stock.services import fail

from .models import Employee, Shift, TimeEntry


def _day_bounds(start: date, end: date):
    a = timezone.make_aware(datetime.combine(start, time.min))
    b = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    return a, b


@transaction.atomic
def clock(location, pin: str):
    """Kiosk clock in/out: the PIN identifies the employee at this location."""
    if not pin or not pin.isdigit() or not 4 <= len(pin) <= 8:
        fail("Enter your 4–8 digit PIN.")
    match = next((e for e in Employee.objects.filter(location=location, is_active=True).exclude(pin_hash="")
                  if e.check_pin(pin)), None)
    if not match:
        fail("PIN not recognised at this location.")
    now = timezone.now()
    open_entry = TimeEntry.objects.select_for_update().filter(employee=match, clock_out__isnull=True).first()
    if open_entry:
        open_entry.clock_out = now
        hours = (now - open_entry.clock_in).total_seconds() / 3600
        if hours > 6 and not open_entry.break_minutes:
            open_entry.break_minutes = 30  # Ontario: 30-minute eating period after 5 hours; managers can edit
        open_entry.save(update_fields=["clock_out", "break_minutes"])
        return match, "out", open_entry
    entry = TimeEntry.objects.create(employee=match, location=location, clock_in=now)
    return match, "in", entry


def tip_pool(location, start: date, end: date) -> dict:
    """Card and cash tips per day shared among tip-pool staff by hours worked that day."""
    from pos.models import Payment

    tips = defaultdict(Decimal)
    for p in Payment.objects.filter(order__location=location, order__business_date__gte=start,
                                    order__business_date__lte=end, status=Payment.Status.APPROVED, tip__gt=0) \
            .select_related("order"):
        tips[p.order.business_date] += p.tip
    a, b = _day_bounds(start, end)
    hours = defaultdict(lambda: defaultdict(float))
    for e in TimeEntry.objects.filter(location=location, clock_in__gte=a, clock_in__lt=b, clock_out__isnull=False,
                                      employee__shares_tips=True).select_related("employee"):
        hours[timezone.localdate(e.clock_in)][e.employee] += e.hours or 0
    shares = defaultdict(Decimal)
    unassigned = Decimal(0)
    for day, total in tips.items():
        worked = hours.get(day, {})
        all_hours = sum(worked.values())
        if not all_hours:
            unassigned += total
            continue
        for emp, h in worked.items():
            shares[emp] += (total * Decimal(str(h / all_hours))).quantize(Decimal("0.01"))
    return {"total": float(sum(tips.values(), Decimal(0))), "unassigned": float(unassigned),
            "shares": sorted(({"employee": e.id, "name": e.name, "amount": float(v)} for e, v in shares.items()),
                             key=lambda r: -r["amount"])}


def timesheet(location, start: date, end: date) -> dict:
    a, b = _day_bounds(start, end)
    entries = list(TimeEntry.objects.filter(location=location, clock_in__gte=a, clock_in__lt=b).select_related("employee"))
    shifts = list(Shift.objects.filter(location=location, date__gte=start, date__lte=end).select_related("employee"))
    sales = {r["day__business_date"]: r["t"] for r in SalesLine.objects.filter(
        day__location=location, day__business_date__gte=start, day__business_date__lte=end
    ).values("day__business_date").order_by().annotate(t=Sum("net_sales"))}

    people = defaultdict(lambda: {"scheduled": 0.0, "worked": 0.0, "cost": 0.0})
    days = defaultdict(lambda: {"hours": 0.0, "cost": 0.0})
    for s in shifts:
        people[s.employee]["scheduled"] += s.hours
    for e in entries:
        h = e.hours or 0
        cost = h * float(e.employee.hourly_rate or 0)
        people[e.employee]["worked"] += h
        people[e.employee]["cost"] += cost
        d = timezone.localdate(e.clock_in)
        days[d]["hours"] += h
        days[d]["cost"] += cost
    day_rows = []
    d = start
    while d <= end:
        s = float(sales.get(d) or 0)
        day_rows.append({"date": d, "sales": s, "hours": round(days[d]["hours"], 2), "cost": round(days[d]["cost"], 2),
                         "labour_pct": days[d]["cost"] / s if s else None, "splh": s / days[d]["hours"] if days[d]["hours"] else None})
        d += timedelta(days=1)
    total_sales = sum(r["sales"] for r in day_rows)
    total_hours = sum(r["hours"] for r in day_rows)
    total_cost = sum(r["cost"] for r in day_rows)
    return {
        "entries": [{"id": e.id, "employee": e.employee_id, "name": e.employee.name, "department": e.employee.get_department_display(),
                     "clock_in": e.clock_in, "clock_out": e.clock_out, "break_minutes": e.break_minutes,
                     "hours": round(e.hours, 2) if e.hours is not None else None, "note": e.note,
                     "edited": bool(e.edited_by_id)} for e in entries],
        "people": sorted(({"employee": emp.id, "name": emp.name, "department": emp.get_department_display(),
                           "rate": float(emp.hourly_rate or 0), "scheduled": round(v["scheduled"], 2),
                           "worked": round(v["worked"], 2), "cost": round(v["cost"], 2)} for emp, v in people.items()),
                         key=lambda r: r["name"]),
        "days": day_rows,
        "totals": {"sales": total_sales, "hours": round(total_hours, 2), "cost": round(total_cost, 2),
                   "labour_pct": total_cost / total_sales if total_sales else None,
                   "splh": total_sales / total_hours if total_hours else None},
        "tips": tip_pool(location, start, end),
    }


def labour_totals(location_ids, start: date, end: date) -> dict:
    """Hours and cost per location, for the performance sheet."""
    a, b = _day_bounds(start, end)
    out = defaultdict(lambda: {"hours": 0.0, "cost": 0.0})
    for e in TimeEntry.objects.filter(location_id__in=location_ids, clock_in__gte=a, clock_in__lt=b,
                                      clock_out__isnull=False).select_related("employee"):
        h = e.hours or 0
        out[e.location_id]["hours"] += h
        out[e.location_id]["cost"] += h * float(e.employee.hourly_rate or 0)
    return out
