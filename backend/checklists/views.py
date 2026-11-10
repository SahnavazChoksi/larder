from datetime import date, timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCook, IsManager, location_from_request, require_location
from audit.services import log
from catalog.models import Location
from stock.services import fail

from . import services
from .models import SOP, ChecklistRun, ChecklistTemplate, RunAnswer, TemplateTask
from .serializers import (
    AnswerIn, AnswerSerializer, RunDetailSerializer, RunSerializer, SOPSerializer, TemplateIn, TemplateSerializer,
)


def _valid(cls, data):
    s = cls(data=data)
    s.is_valid(raise_exception=True)
    return s.validated_data


def _date(value):
    if not value:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail("Dates must look like 2026-11-08.")


def _run(request, pk):
    run = get_object_or_404(ChecklistRun.objects.select_related("template", "location"), pk=pk)
    require_location(request.user, run.location)
    return run


# ---------- today's checklists ----------

@api_view(["GET"])
@permission_classes([IsCook])
def today(request):
    """Checklists due at a location for a date, with their run (if started)."""
    location = location_from_request(request)
    day = _date(request.query_params.get("date"))
    runs = {r.template_id: r for r in ChecklistRun.objects.filter(location=location, business_date=day)}
    out = []
    for t in services.templates_for(location):
        run = runs.get(t.id)
        out.append({
            "template": t.id, "name": t.name, "kind": t.kind, "kind_label": t.get_kind_display(),
            "due_by": t.due_by, "late": services.is_late(t, day) and (not run or run.status == ChecklistRun.Status.IN_PROGRESS),
            "task_count": t.tasks.filter(is_active=True).count(),
            "run": RunSerializer(run).data if run else None,
        })
    return Response({"date": day, "location": location.id, "checklists": out})


class Runs(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        """History: filter by location, status, dates."""
        qs = ChecklistRun.objects.filter(location_id__in=request.user.location_ids()) \
            .select_related("template", "location", "started_by", "submitted_by", "reviewed_by")
        location = location_from_request(request, required=False)
        if location:
            qs = qs.filter(location=location)
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("start"):
            qs = qs.filter(business_date__gte=_date(p["start"]))
        if p.get("end"):
            qs = qs.filter(business_date__lte=_date(p["end"]))
        return Response(RunSerializer(qs.order_by("-business_date", "-id")[:100], many=True).data)

    def post(self, request):
        """Start (or resume) a checklist. Body: template, location, date (optional)."""
        location = location_from_request(request)
        template = get_object_or_404(ChecklistTemplate, pk=request.data.get("template"))
        day = _date(request.data.get("date"))
        if day > timezone.localdate():
            fail("You can't start a checklist for a future day.")
        existed = ChecklistRun.objects.filter(template=template, location=location, business_date=day).exists()
        run = services.start_run(template, location, day, request.user)
        if not existed:
            log(request.user, "Started checklist", f"{template.name} for {day:%b %d}", location)
        return Response(RunDetailSerializer(run).data, status=status.HTTP_201_CREATED if not existed else 200)


@api_view(["GET"])
@permission_classes([IsCook])
def run_detail(request, pk):
    return Response(RunDetailSerializer(_run(request, pk)).data)


@api_view(["PATCH"])
@permission_classes([IsCook])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def answer(request, pk, answer_id):
    """Tick a task, enter a reading, add a note or upload a photo (multipart field 'photo')."""
    run = _run(request, pk)
    ans = get_object_or_404(RunAnswer.objects.select_related("task", "run"), pk=answer_id, run=run)
    raw = request.data
    clear_value = "value" in raw and raw.get("value") in ("", None, "null")
    data = _valid(AnswerIn, {k: v for k, v in raw.items() if not (k == "value" and clear_value)})
    services.update_answer(
        ans, request.user, done=data.get("done"), value=data.get("value"), clear_value=clear_value,
        note=data.get("note"), photo=data.get("photo"),
    )
    if data.get("photo"):
        log(request.user, "Uploaded checklist photo", f"{run.template.name} {run.business_date:%b %d}: {ans.task_text}", run.location)
    return Response(AnswerSerializer(ans).data)


@api_view(["POST"])
@permission_classes([IsCook])
def submit(request, pk):
    run = _run(request, pk)
    found = services.submit_run(run, request.user)
    log(request.user, "Submitted checklist",
        f"{run.template.name} for {run.business_date:%b %d}" + (f". Issues: {'; '.join(found)}" if found else ""), run.location)
    return Response(RunDetailSerializer(run).data)


@api_view(["POST"])
@permission_classes([IsManager])
def review(request, pk):
    """Body: decision = approve | flag | reopen, note."""
    run = _run(request, pk)
    decision, note = request.data.get("decision", ""), request.data.get("note", "") or ""
    services.review_run(run, request.user, decision, note)
    verb = {"approve": "Approved", "flag": "Flagged", "reopen": "Reopened"}[decision]
    log(request.user, f"{verb} checklist",
        f"{run.template.name} for {run.business_date:%b %d}" + (f": {note}" if note else ""), run.location)
    return Response(RunDetailSerializer(run).data)


@api_view(["GET"])
@permission_classes([IsManager])
def compliance(request):
    p = request.query_params
    end = _date(p.get("end"))
    start = _date(p.get("start")) if p.get("start") else end.replace(day=1)
    locations = Location.objects.filter(id__in=request.user.location_ids())
    return Response(services.compliance(list(locations), start, end))


# ---------- templates ----------

class Templates(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else [IsManager()]

    def get(self, request):
        qs = ChecklistTemplate.objects.all() if request.query_params.get("all") else ChecklistTemplate.objects.filter(is_active=True)
        return Response(TemplateSerializer(qs, many=True).data)

    def post(self, request):
        data = _valid(TemplateIn, request.data)
        with transaction.atomic():
            t = ChecklistTemplate.objects.create(
                name=data["name"], kind=data["kind"], applies_to=data["applies_to"], due_by=data.get("due_by"),
                is_active=data["is_active"], updated_by=request.user,
            )
            _save_tasks(t, data["tasks"])
        log(request.user, "Created checklist", f"{t.name}: {len(data['tasks'])} tasks")
        return Response(TemplateSerializer(t).data, status=status.HTTP_201_CREATED)


def _save_tasks(template, tasks):
    """Update tasks in place, add new ones, deactivate removed ones (history keeps pointing at them)."""
    keep = []
    current = {t.id: t for t in template.tasks.all()}
    for pos, data in enumerate(tasks):
        fields = {k: v for k, v in data.items() if k != "id"}
        fields["position"] = pos
        task = current.get(data.get("id"))
        if task:
            for k, v in fields.items():
                setattr(task, k, v)
            task.is_active = True
            task.save()
        else:
            task = TemplateTask.objects.create(template=template, **fields)
        keep.append(task.id)
    template.tasks.exclude(id__in=keep).update(is_active=False)


@api_view(["PUT"])
@permission_classes([IsManager])
def template_detail(request, pk):
    t = get_object_or_404(ChecklistTemplate, pk=pk)
    data = _valid(TemplateIn, request.data)
    with transaction.atomic():
        for field in ("name", "kind", "applies_to", "is_active"):
            setattr(t, field, data[field])
        t.due_by = data.get("due_by")
        t.updated_by = request.user
        t.save()
        _save_tasks(t, data["tasks"])
    log(request.user, "Changed checklist", f"{t.name}: {len(data['tasks'])} tasks" + ("" if t.is_active else " (switched off)"))
    return Response(TemplateSerializer(t).data)


# ---------- SOPs ----------

class Sops(APIView):
    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == "GET" else [IsManager()]

    def get(self, request):
        return Response(SOPSerializer(SOP.objects.filter(is_active=True).select_related("updated_by"), many=True).data)

    def post(self, request):
        s = SOPSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sop = s.save(updated_by=request.user)
        log(request.user, "Added SOP", sop.title)
        return Response(SOPSerializer(sop).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsManager])
def sop_detail(request, pk):
    sop = get_object_or_404(SOP, pk=pk)
    s = SOPSerializer(sop, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    sop = s.save(updated_by=request.user)
    log(request.user, "Updated SOP", sop.title + ("" if sop.is_active else " (archived)"))
    return Response(SOPSerializer(sop).data)


# ---------- readings (temperature log) ----------

@api_view(["GET"])
@permission_classes([IsCook])
def readings(request):
    """Every recorded reading at a location, grouped by what was measured. Printable for inspections."""
    location = location_from_request(request)
    days = min(int(request.query_params.get("days", 30)), 400)
    since = timezone.localdate() - timedelta(days=days)
    answers = (RunAnswer.objects.filter(run__location=location, run__business_date__gte=since, value__isnull=False)
               .exclude(task__value_label="").select_related("task", "run__template", "done_by")
               .order_by("run__business_date", "run__template__kind"))
    series = {}
    for a in answers:
        t = a.task
        s = series.setdefault(t.value_label, {"label": t.value_label, "unit": t.value_unit,
                                              "min": t.value_min, "max": t.value_max, "points": []})
        s["points"].append({
            "date": a.run.business_date, "checklist": a.run.template.name, "kind": a.run.template.kind,
            "value": a.value, "ok": not a.out_of_range, "by": a.done_by.display_name if a.done_by else None,
            "at": a.done_at, "run": a.run_id,
        })
    out = sorted(series.values(), key=lambda s: s["label"])
    for s in out:
        s["out_of_range"] = sum(1 for p in s["points"] if not p["ok"])
    return Response({"location": location.id, "since": since, "series": out})
