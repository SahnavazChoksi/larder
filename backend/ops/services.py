import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import Role, User
from catalog.models import Location

from .models import Department, Employee, Issue, Notification, StaffingPlan

log = logging.getLogger(__name__)


# ---------- notifications ----------

def managers_for(location: Location | None):
    """Active managers who work at the location, plus owners."""
    qs = User.objects.filter(is_active=True).filter(Q(role=Role.OWNER) | Q(role=Role.MANAGER))
    if location is not None:
        qs = qs.filter(Q(role=Role.OWNER) | Q(locations=location))
    return qs.distinct()


def notify(users, title, body="", link="", severity="info", key="", email=True) -> int:
    """In-app notification for each user, plus an email if they have an address.

    `key` makes the alert idempotent per user, so a scheduled job can run repeatedly without spamming.
    """
    sent = 0
    for user in users:
        try:
            with transaction.atomic():
                n = Notification.objects.create(user=user, title=title[:160], body=body[:400], link=link,
                                                severity=severity, key=key[:120])
        except IntegrityError:
            continue  # already told this person
        sent += 1
        if email and user.email:
            try:
                send_mail(f"[Larder] {title}", f"{body}\n\nOpen Larder: {settings.LARDER_APP_URL}{link}",
                          settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
                n.emailed = True
                n.save(update_fields=["emailed"])
            except Exception:  # never let a mail outage break the action that triggered it
                log.exception("Could not email %s", user.email)
    return sent


# ---------- staffing ----------

def staffing(locations) -> dict:
    """Required vs actual headcount per location and department, like a weekly ops sheet."""
    plans = {(p.location_id, p.department): p.required for p in StaffingPlan.objects.filter(location__in=locations)}
    actual = {
        (r["location"], r["department"]): r["n"]
        for r in Employee.objects.filter(location__in=locations, is_active=True)
        .values("location", "department").order_by().annotate(n=Count("id"))
    }
    columns = []
    for loc in locations:
        for dept, label in Department.choices:
            req, act = plans.get((loc.id, dept)), actual.get((loc.id, dept), 0)
            if req is None and not act:
                continue
            columns.append({"location": loc.id, "location_name": loc.name, "department": dept,
                            "department_label": label, "required": req or 0, "actual": act,
                            "gap": max(0, (req or 0) - act)})
    return {
        "columns": columns,
        "total": {k: sum(c[k] for c in columns) for k in ("required", "actual", "gap")},
    }


# ---------- issues ----------

def raise_issue_for_answer(answer, user) -> Issue | None:
    """A critical checklist reading failed: open (or reuse) an issue and tell managers."""
    run, task = answer.run, answer.task
    existing = Issue.objects.filter(location=run.location, title__startswith=task.value_label or task.text,
                                    status__in=[Issue.Status.OPEN, Issue.Status.IN_PROGRESS]).first()
    detail = (f"{run.template.name} on {run.business_date:%b %d}: {task.value_label or task.text} read "
              f"{answer.value}{task.value_unit}." + (f" Note: {answer.note}" if answer.note else ""))
    if existing:
        existing.detail += "\n" + detail
        existing.save(update_fields=["detail"])
        return None
    issue = Issue.objects.create(
        location=run.location, title=f"{task.value_label or task.text} out of range",
        detail=detail, severity=Issue.Severity.CRITICAL, source_answer=answer, raised_by=user,
    )
    notify(managers_for(run.location), f"{issue.title} at {run.location.name}", detail,
           link=f"/issues?location={run.location_id}", severity="bad", key=f"issue-{issue.id}")
    return issue


# ---------- scheduled checks ----------

def daily_alerts() -> int:
    """Run hourly (cron / Task Scheduler): missed checklists, overdue openings, low stock, old open issues."""
    from checklists.services import compliance
    from stock.services import on_hand_map, par_map, stock_status

    today = timezone.localdate()
    sent = 0
    locations = list(Location.objects.all())
    for m in compliance(locations, today - timedelta(days=1), today)["missing"]:
        loc = next(x for x in locations if x.id == m["location"])
        sent += notify(managers_for(loc), f"{m['template']} not done at {loc.name}",
                       f"Nothing was submitted for {m['date']:%a %b %d}.", link=f"/checklists?location={loc.id}",
                       severity="bad", key=f"missed-{m['template']}-{loc.id}-{m['date']}")
    for loc in locations:
        stock, pars = on_hand_map(loc), par_map(loc)
        low = [i for i, p in pars.items() if stock_status(stock.get(i, 0), p) in ("out",)]
        if low:
            sent += notify(managers_for(loc), f"{len(low)} item{'s' if len(low) > 1 else ''} out of stock at {loc.name}",
                           "Check Stock & counts and Purchasing.", link=f"/stock?location={loc.id}",
                           severity="warn", key=f"out-{loc.id}-{today}")
    stale = Issue.objects.filter(status=Issue.Status.OPEN, severity=Issue.Severity.CRITICAL,
                                 created_at__lt=timezone.now() - timedelta(hours=24))
    for issue in stale.select_related("location"):
        sent += notify(managers_for(issue.location), f"Still open after 24 h: {issue.title}",
                       f"{issue.location.name}. Assign someone to fix it.", link=f"/issues?location={issue.location_id}",
                       severity="bad", key=f"stale-{issue.id}-{today}")
    return sent
