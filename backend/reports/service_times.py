"""Where guests wait: from walking in to paying. Built from POS, kitchen ticket and waitlist timestamps.

Seating wait   waitlist added → seated            (host stand)
Order wait     check opened → first send to kitchen (server)
Kitchen queue  ticket sent → cook starts it         (kitchen)
Prep           ticket sent → ready                  (kitchen)
At the pass    ready → served                        (runners)
Table time     check opened → paid                   (whole visit)
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from guests.models import WaitlistEntry
from pos.models import Order, Ticket

STAGES = [
    ("seating", "Wait to be seated"),
    ("order", "Seated → order sent"),
    ("queue", "Waiting for a cook"),
    ("prep", "Cooking (sent → ready)"),
    ("pass", "Ready → served"),
    ("table", "Table time (seated → paid)"),
]


def _mins(a, b):
    return (b - a).total_seconds() / 60 if a and b and b >= a else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _p90(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(len(xs) * 0.9))] if xs else None


def service_times(location, start: date, end: date) -> dict:
    a = timezone.make_aware(datetime.combine(start, time.min))
    b = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min))
    samples = defaultdict(list)          # stage -> minutes
    by_hour = defaultdict(lambda: defaultdict(list))  # stage -> hour -> minutes
    weekday_vs_weekend = defaultdict(lambda: {"weekday": [], "weekend": []})

    def add(stage, minutes, when):
        if minutes is None:
            return
        local = timezone.localtime(when)
        samples[stage].append(minutes)
        by_hour[stage][local.hour].append(minutes)
        weekday_vs_weekend[stage]["weekend" if local.weekday() >= 4 else "weekday"].append(minutes)

    for w in WaitlistEntry.objects.filter(location=location, added_at__gte=a, added_at__lt=b, seated_at__isnull=False):
        add("seating", _mins(w.added_at, w.seated_at), w.added_at)
    for o in Order.objects.filter(location=location, opened_at__gte=a, opened_at__lt=b, type=Order.Type.DINE_IN) \
            .exclude(status=Order.Status.VOID):
        add("order", _mins(o.opened_at, o.first_sent_at), o.opened_at)
        add("table", _mins(o.opened_at, o.closed_at), o.opened_at)
    tickets = list(Ticket.objects.filter(location=location, sent_at__gte=a, sent_at__lt=b).exclude(status=Ticket.Status.VOID))
    for t in tickets:
        add("queue", _mins(t.sent_at, t.started_at), t.sent_at)
        add("prep", _mins(t.sent_at, t.ready_at), t.sent_at)
        add("pass", _mins(t.ready_at, t.served_at), t.sent_at)

    target = settings.TICKET_TARGET_MINUTES
    prep = samples["prep"]
    hours = sorted({h for stage in by_hour.values() for h in stage})
    waits = list(WaitlistEntry.objects.filter(location=location, added_at__gte=a, added_at__lt=b, seated_at__isnull=False))
    return {
        "stages": [{"key": k, "label": label, "count": len(samples[k]), "avg": _avg(samples[k]), "p90": _p90(samples[k]),
                    "weekday": _avg(weekday_vs_weekend[k]["weekday"]), "weekend": _avg(weekday_vs_weekend[k]["weekend"])}
                   for k, label in STAGES],
        "hours": hours,
        "by_hour": {k: [{"hour": h, "avg": _avg(by_hour[k][h]), "count": len(by_hour[k][h])} for h in hours] for k, _ in STAGES},
        "kitchen": {"target": target, "tickets": len(prep), "late": sum(1 for m in prep if m > target),
                    "late_pct": sum(1 for m in prep if m > target) / len(prep) if prep else None},
        "quotes": {"parties": len(waits), "over_quote": sum(1 for w in waits if (w.waited_minutes or 0) > w.quoted_minutes + 2),
                   "avg_quoted": _avg([w.quoted_minutes for w in waits]), "avg_actual": _avg([w.waited_minutes for w in waits])},
    }
