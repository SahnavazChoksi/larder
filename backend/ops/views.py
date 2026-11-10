from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCook, IsManager, location_from_request, require_location
from audit.services import log
from catalog.models import Location

from . import services
from .models import (
    Complaint, DeliveryScore, Department, Employee, Equipment, HandoverNote, Issue, Notification, StaffingPlan,
)


def _name(user):
    return user.display_name if user else None


def _scoped(qs, request, field="location"):
    qs = qs.filter(**{f"{field}_id__in": request.user.location_ids()})
    location = location_from_request(request, required=False)
    return qs.filter(**{field: location}) if location else qs


# ---------- staffing ----------

class EmployeeSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    department_label = serializers.CharField(source="get_department_display", read_only=True)
    pin = serializers.RegexField(r"^\d{4,8}$", write_only=True, required=False,
                                 error_messages={"invalid": "PINs are 4 to 8 digits."})
    has_pin = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "location", "location_name", "department", "department_label", "name", "position",
                  "started_on", "left_on", "is_active", "hourly_rate", "shares_tips", "pin", "has_pin"]

    def get_has_pin(self, e):
        return bool(e.pin_hash)

    def _pin(self, e, pin):
        if pin:
            clash = Employee.objects.filter(location=e.location, is_active=True).exclude(pk=e.pk)
            if any(other.check_pin(pin) for other in clash):
                raise serializers.ValidationError({"pin": "Someone at this location already uses that PIN."})
            e.set_pin(pin)
            e.save(update_fields=["pin_hash"])

    def create(self, data):
        pin = data.pop("pin", None)
        e = super().create(data)
        self._pin(e, pin)
        return e

    def update(self, e, data):
        pin = data.pop("pin", None)
        e = super().update(e, data)
        self._pin(e, pin)
        return e


@api_view(["GET"])
@permission_classes([IsManager])
def staffing(request):
    location = location_from_request(request, required=False)
    locations = [location] if location else list(Location.objects.filter(id__in=request.user.location_ids()))
    return Response(services.staffing(locations))


@api_view(["POST"])
@permission_classes([IsManager])
def staffing_plan(request):
    """Body: {location, department, required}"""
    location = location_from_request(request)
    dept = request.data.get("department")
    if dept not in Department.values:
        raise serializers.ValidationError({"department": "Unknown department."})
    try:
        required = int(request.data.get("required"))
        assert 0 <= required <= 500
    except (TypeError, ValueError, AssertionError):
        raise serializers.ValidationError({"required": "Enter a whole number from 0 to 500."}) from None
    plan, _ = StaffingPlan.objects.update_or_create(location=location, department=dept,
                                                    defaults={"required": required, "updated_by": request.user})
    log(request.user, "Changed staffing plan", f"{plan.get_department_display()}: {required} people", location)
    return Response({"required": required})


class Employees(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        qs = _scoped(Employee.objects.select_related("location"), request)
        if request.query_params.get("all") != "1":
            qs = qs.filter(is_active=True)
        return Response(EmployeeSerializer(qs, many=True).data)

    def post(self, request):
        s = EmployeeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        e = s.save()
        log(request.user, "Added employee", f"{e.name}, {e.get_department_display()}", e.location)
        return Response(EmployeeSerializer(e).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsManager])
def employee_detail(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    require_location(request.user, e.location)
    s = EmployeeSerializer(e, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    if "location" in s.validated_data:
        require_location(request.user, s.validated_data["location"])
    if s.validated_data.get("is_active") is False and not s.validated_data.get("left_on"):
        s.validated_data["left_on"] = timezone.localdate()
    e = s.save()
    log(request.user, "Updated employee", f"{e.name}" + ("" if e.is_active else " (left)"), e.location)
    return Response(EmployeeSerializer(e).data)


# ---------- complaints ----------

class ComplaintSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    logged_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = ["id", "location", "location_name", "occurred_on", "category", "category_label", "channel",
                  "channel_label", "detail", "action_taken", "comped", "logged_by_name"]

    def get_logged_by_name(self, c):
        return _name(c.logged_by)


class Complaints(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        since = timezone.localdate() - timedelta(days=int(request.query_params.get("days", 60)))
        qs = _scoped(Complaint.objects.filter(occurred_on__gte=since).select_related("location", "logged_by"), request)
        return Response(ComplaintSerializer(qs[:300], many=True).data)

    def post(self, request):
        s = ComplaintSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        c = s.save(logged_by=request.user)
        log(request.user, "Logged complaint", f"{c.get_category_display()}: {c.detail}", c.location)
        return Response(ComplaintSerializer(c).data, status=status.HTTP_201_CREATED)


# ---------- equipment & issues ----------

class EquipmentSerializer(serializers.ModelSerializer):
    open_issues = serializers.SerializerMethodField()

    class Meta:
        model = Equipment
        fields = ["id", "location", "name", "category", "serial", "service_contact", "is_active", "open_issues"]

    def get_open_issues(self, e):
        return e.issues.exclude(status=Issue.Status.RESOLVED).count()


class IssueSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    equipment_name = serializers.CharField(source="equipment.name", read_only=True, default=None)
    severity_label = serializers.CharField(source="get_severity_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    raised_by_name = serializers.SerializerMethodField()
    checklist_run = serializers.IntegerField(source="source_answer.run_id", read_only=True, default=None)

    class Meta:
        model = Issue
        fields = ["id", "number", "location", "location_name", "equipment", "equipment_name", "title", "detail",
                  "severity", "severity_label", "status", "status_label", "assigned_to", "raised_by_name",
                  "created_at", "resolved_at", "resolution", "repair_cost", "checklist_run"]
        read_only_fields = ["resolved_at"]

    def get_raised_by_name(self, i):
        return _name(i.raised_by)


class EquipmentView(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "POST" else [IsCook()]

    def get(self, request):
        return Response(EquipmentSerializer(_scoped(Equipment.objects.filter(is_active=True), request), many=True).data)

    def post(self, request):
        s = EquipmentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        e = s.save()
        log(request.user, "Added equipment", e.name, e.location)
        return Response(EquipmentSerializer(e).data, status=status.HTTP_201_CREATED)


class Issues(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        qs = _scoped(Issue.objects.select_related("location", "equipment", "raised_by", "source_answer"), request)
        if request.query_params.get("status") == "open":
            qs = qs.exclude(status=Issue.Status.RESOLVED)
        return Response(IssueSerializer(qs[:200], many=True).data)

    def post(self, request):
        """Anyone on shift can report a problem."""
        s = IssueSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        issue = s.save(raised_by=request.user, status=Issue.Status.OPEN)
        log(request.user, "Reported issue", f"{issue.number}: {issue.title} ({issue.get_severity_display()})", issue.location)
        if issue.severity != Issue.Severity.LOW:
            services.notify(services.managers_for(issue.location), f"{issue.title} at {issue.location.name}",
                            issue.detail or f"Reported by {request.user.display_name}.",
                            link=f"/issues?location={issue.location_id}", severity="bad" if issue.severity == "critical" else "warn",
                            key=f"issue-{issue.id}")
        return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsManager])
def issue_detail(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    require_location(request.user, issue.location)
    before = issue.status
    s = IssueSerializer(issue, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    issue = s.save()
    if issue.status == Issue.Status.RESOLVED and before != Issue.Status.RESOLVED:
        issue.resolved_at = timezone.now()
        issue.save(update_fields=["resolved_at"])
    elif issue.status != Issue.Status.RESOLVED and issue.resolved_at:
        issue.resolved_at = None
        issue.save(update_fields=["resolved_at"])
    log(request.user, "Updated issue", f"{issue.number}: {issue.get_status_display()}"
        + (f" — {issue.resolution}" if issue.resolution and issue.status == Issue.Status.RESOLVED else ""), issue.location)
    return Response(IssueSerializer(issue).data)


# ---------- handover logbook ----------

class NoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    shift_label = serializers.CharField(source="get_shift_display", read_only=True)
    read = serializers.SerializerMethodField()
    read_count = serializers.IntegerField(source="read_by.count", read_only=True)

    class Meta:
        model = HandoverNote
        fields = ["id", "location", "business_date", "shift", "shift_label", "body", "is_important",
                  "author_name", "created_at", "read", "read_count"]

    def get_author_name(self, n):
        return _name(n.author)

    def get_read(self, n):
        user = self.context.get("user")
        return bool(user) and (n.author_id == user.id or n.read_by.filter(id=user.id).exists())


class Handover(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        since = timezone.localdate() - timedelta(days=int(request.query_params.get("days", 7)))
        qs = HandoverNote.objects.filter(location=location, business_date__gte=since).select_related("author")
        return Response(NoteSerializer(qs, many=True, context={"user": request.user}).data)

    def post(self, request):
        s = NoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        note = s.save(author=request.user)
        log(request.user, "Wrote handover note", note.body[:120], note.location)
        if note.is_important:
            services.notify(services.managers_for(note.location).exclude(id=request.user.id),
                            f"Important handover note at {note.location.name}", note.body[:300],
                            link=f"/logbook?location={note.location_id}", severity="warn", key=f"note-{note.id}", email=False)
        return Response(NoteSerializer(note, context={"user": request.user}).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsCook])
def handover_read(request, pk):
    note = get_object_or_404(HandoverNote, pk=pk)
    require_location(request.user, note.location)
    note.read_by.add(request.user)
    return Response({"read": True})


# ---------- notifications ----------

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "link", "severity", "created_at", "read_at"]


@api_view(["GET"])
def notifications(request):
    qs = Notification.objects.filter(user=request.user)
    return Response({
        "unread": qs.filter(read_at__isnull=True).count(),
        "items": NotificationSerializer(qs[:30], many=True).data,
    })


@api_view(["POST"])
def notifications_read(request):
    """Body: {"ids": [...]} or {} for all."""
    qs = Notification.objects.filter(user=request.user, read_at__isnull=True)
    ids = request.data.get("ids")
    if ids:
        qs = qs.filter(id__in=ids)
    return Response({"marked": qs.update(read_at=timezone.now())})


# ---------- delivery app scores ----------

class DeliveryScoreSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    platform_label = serializers.CharField(source="get_platform_display", read_only=True)

    class Meta:
        model = DeliveryScore
        fields = ["id", "location", "location_name", "platform", "platform_label", "week_start", "orders", "ready_accuracy", "rating"]
        validators = []  # we upsert instead of rejecting duplicates

    def validate_ready_accuracy(self, v):
        if v is not None and not 0 <= v <= 100:
            raise serializers.ValidationError("Enter a percentage from 0 to 100.")
        return v

    def validate_rating(self, v):
        if v is not None and not 0 <= v <= 5:
            raise serializers.ValidationError("Ratings are 0 to 5.")
        return v

    def validate_week_start(self, v):
        return v - timedelta(days=v.weekday())  # always store the Monday


class DeliveryScores(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        since = timezone.localdate() - timedelta(weeks=int(request.query_params.get("weeks", 8)))
        qs = _scoped(DeliveryScore.objects.filter(week_start__gte=since).select_related("location"), request)
        return Response(DeliveryScoreSerializer(qs, many=True).data)

    def post(self, request):
        """Add or replace one week's score for a location and platform."""
        s = DeliveryScoreSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        require_location(request.user, d["location"])
        score, _ = DeliveryScore.objects.update_or_create(
            location=d["location"], platform=d["platform"], week_start=d["week_start"],
            defaults={"orders": d.get("orders", 0), "ready_accuracy": d.get("ready_accuracy"), "rating": d.get("rating"),
                      "entered_by": request.user},
        )
        log(request.user, "Entered delivery score",
            f"{score.get_platform_display()} week of {score.week_start:%b %d}: {score.ready_accuracy}% ready accuracy", score.location)
        return Response(DeliveryScoreSerializer(score).data, status=status.HTTP_201_CREATED)


# ---------- scheduling, time clock, timesheets ----------

from datetime import date as _date  # noqa: E402

from . import labour  # noqa: E402
from .models import Shift, TimeEntry  # noqa: E402


def _parse_date(value, default):
    if not value:
        return default
    try:
        return _date.fromisoformat(value)
    except ValueError:
        raise serializers.ValidationError({"date": "Dates must look like 2026-11-08."}) from None


class ShiftSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.name", read_only=True)
    hours = serializers.FloatField(read_only=True)

    class Meta:
        model = Shift
        fields = ["id", "employee", "employee_name", "location", "date", "start", "end", "role", "published", "hours"]
        read_only_fields = ["published"]

    def validate(self, data):
        emp, loc = data.get("employee") or self.instance.employee, data.get("location") or self.instance.location
        if emp.location_id != loc.id:
            raise serializers.ValidationError("That employee works at another location.")
        return data


class Shifts(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        location = location_from_request(request)
        today = timezone.localdate()
        week = _parse_date(request.query_params.get("week_start"), today - timedelta(days=today.weekday()))
        qs = Shift.objects.filter(location=location, date__gte=week, date__lt=week + timedelta(days=7)).select_related("employee")
        people = Employee.objects.filter(location=location, is_active=True)
        return Response({"week_start": week, "shifts": ShiftSerializer(qs, many=True).data,
                         "employees": EmployeeSerializer(people, many=True).data})

    def post(self, request):
        s = ShiftSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        shift = s.save(created_by=request.user)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsManager])
def shift_detail(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    require_location(request.user, shift.location)
    if request.method == "DELETE":
        shift.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    s = ShiftSerializer(shift, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    return Response(ShiftSerializer(s.save()).data)


@api_view(["POST"])
@permission_classes([IsManager])
def publish_week(request):
    location = location_from_request(request)
    week = _parse_date(request.data.get("week_start"), None)
    if not week:
        raise serializers.ValidationError({"week_start": "Choose a week."})
    shifts = Shift.objects.filter(location=location, date__gte=week, date__lt=week + timedelta(days=7))
    n = shifts.update(published=True)
    log(request.user, "Published schedule", f"Week of {week:%b %d}: {n} shifts", location)
    return Response({"published": n})


class Clock(APIView):
    """Shared kiosk: anyone logged in on the restaurant tablet can open it; the PIN says who is clocking."""

    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        on = TimeEntry.objects.filter(location=location, clock_out__isnull=True).select_related("employee")
        today = timezone.localdate()
        upcoming = Shift.objects.filter(location=location, date=today, published=True).select_related("employee")
        return Response({
            "on_shift": [{"name": e.employee.name, "department": e.employee.get_department_display(), "since": e.clock_in} for e in on],
            "today": ShiftSerializer(upcoming, many=True).data,
        })

    def post(self, request):
        location = location_from_request(request)
        emp, direction, entry = labour.clock(location, str(request.data.get("pin", "")))
        log(request.user, f"Clocked {direction}", emp.name, location)
        return Response({"name": emp.name, "direction": direction, "at": entry.clock_out if direction == "out" else entry.clock_in,
                         "hours": round(entry.hours, 2) if direction == "out" else None})


@api_view(["GET"])
@permission_classes([IsManager])
def timesheets(request):
    location = location_from_request(request)
    today = timezone.localdate()
    start = _parse_date(request.query_params.get("start"), today - timedelta(days=today.weekday()))
    end = _parse_date(request.query_params.get("end"), today)
    if end < start or (end - start).days > 62:
        raise serializers.ValidationError({"date": "Pick up to two months."})
    return Response(labour.timesheet(location, start, end))


class TimeEntryIn(serializers.ModelSerializer):
    class Meta:
        model = TimeEntry
        fields = ["employee", "location", "clock_in", "clock_out", "break_minutes", "note"]

    def validate(self, data):
        a = data.get("clock_in") or self.instance.clock_in
        b = data.get("clock_out", getattr(self.instance, "clock_out", None))
        if b and b <= a:
            raise serializers.ValidationError("Clock-out must be after clock-in.")
        return data


@api_view(["POST"])
@permission_classes([IsManager])
def time_entry_create(request):
    s = TimeEntryIn(data=request.data)
    s.is_valid(raise_exception=True)
    require_location(request.user, s.validated_data["location"])
    e = s.save(edited_by=request.user)
    log(request.user, "Added time entry", f"{e.employee.name}: {e.hours or 0:.2f} h", e.location)
    return Response({"id": e.id}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsManager])
def time_entry_detail(request, pk):
    e = get_object_or_404(TimeEntry, pk=pk)
    require_location(request.user, e.location)
    before = f"{timezone.localtime(e.clock_in):%H:%M}–{timezone.localtime(e.clock_out):%H:%M}" if e.clock_out else "open"
    s = TimeEntryIn(e, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    e = s.save(edited_by=request.user)
    after = f"{timezone.localtime(e.clock_in):%H:%M}–{timezone.localtime(e.clock_out):%H:%M}" if e.clock_out else "open"
    log(request.user, "Edited time entry", f"{e.employee.name} {timezone.localdate(e.clock_in):%b %d}: {before} → {after}", e.location)
    return Response({"id": e.id, "hours": e.hours})
