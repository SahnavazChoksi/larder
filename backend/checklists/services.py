from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from catalog.models import Location
from stock.services import fail

from .models import ChecklistRun, ChecklistTemplate, RunAnswer

MAX_PHOTO_BYTES = 8 * 1024 * 1024


def templates_for(location: Location):
    return [t for t in ChecklistTemplate.objects.filter(is_active=True) if t.applies(location)]


@transaction.atomic
def start_run(template: ChecklistTemplate, location: Location, business_date: date, user) -> ChecklistRun:
    """Open today's checklist (or return the one already open) with one answer per active task."""
    if not template.is_active or not template.applies(location):
        fail(f"'{template.name}' isn't used at {location.name}.")
    run, _ = ChecklistRun.objects.get_or_create(
        template=template, location=location, business_date=business_date, defaults={"started_by": user},
    )
    existing = set(run.answers.values_list("task_id", flat=True))
    RunAnswer.objects.bulk_create(
        RunAnswer(run=run, task=t, task_text=t.text) for t in template.tasks.filter(is_active=True) if t.id not in existing
    )
    return run


def _editable(run: ChecklistRun):
    if run.status != ChecklistRun.Status.IN_PROGRESS:
        fail(f"{run.template.name} for {run.business_date:%b %d} was already submitted. A manager can reopen it.")


def update_answer(answer: RunAnswer, user, *, done=None, value=None, clear_value=False, note=None, photo=None) -> RunAnswer:
    _editable(answer.run)
    if photo is not None:
        if photo.size > MAX_PHOTO_BYTES:
            fail("That photo is over 8 MB. Take it again at a lower resolution.")
        if answer.photo:
            answer.photo.delete(save=False)
        answer.photo = photo
    if clear_value:
        answer.value = None
    elif value is not None:
        answer.value = value
    if note is not None:
        answer.note = note
    if done is not None:
        answer.done = done
        answer.done_by = user if done else None
        answer.done_at = timezone.now() if done else None
    answer.save()
    return answer


def problems(run: ChecklistRun) -> list[str]:
    """What stops a run being submitted."""
    out = []
    for a in run.answers.select_related("task"):
        if not a.done:
            out.append(f"Not done: {a.task_text}")
        elif a.task.requires_photo and not a.photo:
            out.append(f"Photo needed: {a.task_text}")
        elif a.task.value_label and a.value is None:
            out.append(f"Reading needed: {a.task.value_label}")
    return out


def issues(run: ChecklistRun) -> list[str]:
    """Things a manager should look at in a submitted run."""
    out = []
    for a in run.answers.select_related("task"):
        if a.value is not None and a.out_of_range:
            t = a.task
            bounds = " to ".join(str(b) for b in (t.value_min, t.value_max) if b is not None)
            out.append(f"{t.value_label or a.task_text}: {a.value}{t.value_unit} (should be {bounds}{t.value_unit})")
        if a.note:
            out.append(f"Note on '{a.task_text}': {a.note}")
    return out


@transaction.atomic
def submit_run(run: ChecklistRun, user) -> list[str]:
    _editable(run)
    missing = problems(run)
    if missing:
        fail("Finish these first: " + "; ".join(missing[:6]) + ("…" if len(missing) > 6 else ""))
    run.status = ChecklistRun.Status.SUBMITTED
    run.submitted_by, run.submitted_at = user, timezone.now()
    run.save(update_fields=["status", "submitted_by", "submitted_at"])
    return issues(run)


@transaction.atomic
def review_run(run: ChecklistRun, user, decision: str, note="") -> ChecklistRun:
    if decision not in ("approve", "flag", "reopen"):
        fail("Choose approve, flag or reopen.")
    if run.status == ChecklistRun.Status.IN_PROGRESS:
        fail("This checklist hasn't been submitted yet.")
    if decision == "flag" and not note.strip():
        fail("Say what was wrong so the team can fix it.")
    if decision == "reopen":
        run.status = ChecklistRun.Status.IN_PROGRESS
        run.submitted_at = None
    else:
        run.status = ChecklistRun.Status.APPROVED if decision == "approve" else ChecklistRun.Status.FLAGGED
    run.reviewed_by, run.reviewed_at, run.review_note = user, timezone.now(), note.strip()
    run.save(update_fields=["status", "submitted_at", "reviewed_by", "reviewed_at", "review_note"])
    return run


def is_late(template: ChecklistTemplate, business_date: date, now=None) -> bool:
    if not template.due_by:
        return business_date < timezone.localdate()
    now = now or timezone.localtime()
    due = timezone.make_aware(datetime.combine(business_date, template.due_by))
    return now > due


def compliance(locations, start: date, end: date) -> dict:
    """Expected checklists vs what was submitted, per location, over a date range."""
    runs = ChecklistRun.objects.filter(location__in=locations, business_date__gte=start, business_date__lte=end)
    done = {(r.template_id, r.location_id, r.business_date): r for r in runs}
    templates = list(ChecklistTemplate.objects.filter(is_active=True))
    rows, missing = [], []
    for loc in locations:
        expected = submitted = 0
        d = start
        while d <= end:
            for t in templates:
                if not t.applies(loc) or not is_late(t, d):
                    continue
                expected += 1
                run = done.get((t.id, loc.id, d))
                if run and run.status != ChecklistRun.Status.IN_PROGRESS:
                    submitted += 1
                else:
                    missing.append({"location": loc.id, "location_name": loc.name, "template": t.name, "date": d})
            d += timedelta(days=1)
        rows.append({"location": loc.id, "name": loc.name, "expected": expected, "submitted": submitted,
                     "rate": submitted / expected if expected else None})
    return {"locations": rows, "missing": missing}


def alerts(locations) -> list[dict]:
    """Checklist alerts for the dashboard: missed checklists, failed readings, flags, reviews waiting."""
    today = timezone.localdate()
    out = []
    comp = compliance(locations, today - timedelta(days=2), today)
    for m in comp["missing"]:
        out.append({"severity": "bad", "title": f"{m['template']} not done at {m['location_name']}",
                    "detail": f"Nothing submitted for {m['date']:%a %b %d}.", "link": f"/checklists?location={m['location']}"})
    recent = ChecklistRun.objects.filter(location__in=locations, business_date__gte=today - timedelta(days=2)) \
        .exclude(status=ChecklistRun.Status.IN_PROGRESS).select_related("template", "location")
    for run in recent:
        bad = [a for a in run.answers.select_related("task") if a.task.is_critical and a.value is not None and a.out_of_range]
        if bad:
            out.append({"severity": "bad", "title": f"Out-of-range reading at {run.location.name}",
                        "detail": "; ".join(f"{a.task.value_label}: {a.value}{a.task.value_unit}" for a in bad)
                        + f" ({run.template.name}, {run.business_date:%b %d})",
                        "link": f"/checklists?location={run.location_id}&run={run.id}"})
        if run.status == ChecklistRun.Status.FLAGGED:
            out.append({"severity": "warn", "title": f"{run.template.name} flagged at {run.location.name}",
                        "detail": run.review_note, "link": f"/checklists?location={run.location_id}&run={run.id}"})
    waiting = ChecklistRun.objects.filter(location__in=locations, status=ChecklistRun.Status.SUBMITTED).count()
    if waiting:
        out.append({"severity": "info", "title": f"{waiting} checklist{'s' if waiting > 1 else ''} waiting for review",
                    "detail": "Check the photos and readings, then approve or flag.", "link": "/checklists?tab=review"})
    return out
