from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCook, IsManager, location_from_request, require_location
from audit.services import log
from pos import services as pos
from pos.models import Order, Table
from stock.services import fail

from . import messaging
from .models import Guest, PointsEntry, Reservation, WaitlistEntry


class GuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guest
        fields = ["id", "name", "phone", "email", "birthday", "allergies", "notes", "is_member", "joined_on",
                  "marketing_opt_in", "points", "visits", "total_spent", "last_visit"]
        read_only_fields = ["points", "visits", "total_spent", "last_visit", "joined_on"]


class Guests(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        qs = Guest.objects.all()
        if q:
            digits = "".join(c for c in q if c.isdigit())
            cond = Q(name__icontains=q) | Q(email__icontains=q)
            if len(digits) >= 3:
                cond |= Q(phone__contains=digits)
            qs = qs.filter(cond)
        else:
            qs = qs.order_by("-last_visit")
        return Response(GuestSerializer(qs[:50], many=True).data)

    def post(self, request):
        s = GuestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        g = s.save(joined_on=timezone.localdate() if s.validated_data.get("is_member") else None)
        log(request.user, "Added guest", g.name + (" (loyalty member)" if g.is_member else ""))
        return Response(GuestSerializer(g).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsCook])
def guest_detail(request, pk):
    g = get_object_or_404(Guest, pk=pk)
    if request.method == "PATCH":
        was_member = g.is_member
        s = GuestSerializer(g, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        g = s.save()
        if g.is_member and not was_member:
            g.joined_on = timezone.localdate()
            g.save(update_fields=["joined_on"])
            log(request.user, "Enrolled guest in loyalty", g.name)
    from django.db.models import Count, Sum

    from pos.models import OrderLine

    closed = Order.objects.filter(guest=g, status=Order.Status.CLOSED)
    orders = closed.select_related("location", "table", "server").prefetch_related("lines").order_by("-closed_at")[:15]
    favourites = (OrderLine.objects.filter(order__in=closed).exclude(status=OrderLine.Status.VOID)
                  .values("name").order_by().annotate(qty=Sum("qty"), visits=Count("order", distinct=True)).order_by("-qty")[:6])
    return Response({
        **GuestSerializer(g).data,
        "history": [{
            "id": o.id, "number": o.number, "date": o.business_date, "location": o.location.name,
            "type": o.get_type_display(), "table": o.table.name if o.table else None, "guests": o.guests,
            "server": o.server.display_name if o.server else None, "total": float(o.total), "tips": float(o.tips()),
            "discount": float(o.discount), "discount_reason": o.discount_reason,
            "items": [{"name": line.name, "qty": line.qty, "note": line.note, "price": float(line.unit_price)}
                      for line in o.lines.all() if line.status != OrderLine.Status.VOID],
        } for o in orders],
        "order_count": closed.count(),
        "favourites": [{"name": f["name"], "qty": f["qty"], "visits": f["visits"]} for f in favourites],
        "points_history": [{"points": p.points, "reason": p.reason, "at": p.created_at} for p in g.points_history.all()[:20]],
        "reward_points": settings.LOYALTY_REWARD_POINTS, "reward_value": float(settings.LOYALTY_REWARD_VALUE),
    })


@api_view(["POST"])
@permission_classes([IsManager])
def adjust_points(request, pk):
    g = get_object_or_404(Guest, pk=pk)
    try:
        points = int(request.data.get("points"))
    except (TypeError, ValueError):
        fail("Points must be a whole number.")
    reason = str(request.data.get("reason", "")).strip()
    if not reason:
        fail("Say why points are being adjusted.")
    if g.points + points < 0:
        fail("That would take the balance below zero.")
    g.points += points
    g.save(update_fields=["points"])
    PointsEntry.objects.create(guest=g, points=points, reason=reason, created_by=request.user)
    log(request.user, "Adjusted loyalty points", f"{g.name}: {points:+d} ({reason})")
    return Response(GuestSerializer(g).data)


# ---------- seating (shared by reservations and the waitlist) ----------

def _seat(request, location, table_id, party, name, guest, phone=""):
    table = get_object_or_404(Table, pk=table_id, location=location)
    if party > table.seats + 2:
        fail(f"{table.name} seats {table.seats}. Pick a bigger table or push tables together.")
    return pos.open_order(location, request.user, table=table, guests=party, guest=guest, customer_name=name,
                          customer_phone=phone)


# ---------- reservations ----------

class ReservationSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    table_name = serializers.CharField(source="table.name", read_only=True, default=None)

    class Meta:
        model = Reservation
        fields = ["id", "location", "guest", "name", "phone", "party_size", "starts_at", "duration_minutes", "status",
                  "status_label", "table", "table_name", "notes", "arrived_at", "seated_at"]
        read_only_fields = ["status", "arrived_at", "seated_at"]


class Reservations(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        day = request.query_params.get("date")
        day = datetime.fromisoformat(day).date() if day else timezone.localdate()
        start = timezone.make_aware(datetime.combine(day, time.min))
        qs = Reservation.objects.filter(location=location, starts_at__gte=start, starts_at__lt=start + timedelta(days=1)) \
            .select_related("table")
        return Response(ReservationSerializer(qs, many=True).data)

    def post(self, request):
        s = ReservationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        if s.validated_data["starts_at"] < timezone.now() - timedelta(hours=1):
            fail("That time has already passed.")
        r = s.save(created_by=request.user)
        log(request.user, "Booked reservation", f"{r.name}, {r.party_size} people, {timezone.localtime(r.starts_at):%b %d %H:%M}", r.location)
        return Response(ReservationSerializer(r).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsCook])
def reservation_action(request, pk, action):
    r = get_object_or_404(Reservation.objects.select_related("location"), pk=pk)
    require_location(request.user, r.location)
    now = timezone.now()
    if action == "arrive":
        r.status, r.arrived_at = Reservation.Status.ARRIVED, now
    elif action == "seat":
        order = _seat(request, r.location, request.data.get("table") or r.table_id, r.party_size, r.name, r.guest, r.phone)
        r.status, r.seated_at, r.table = Reservation.Status.SEATED, now, order.table
        r.arrived_at = r.arrived_at or now
        r.save()
        return Response({**ReservationSerializer(r).data, "order": order.id})
    elif action in ("no_show", "cancel"):
        r.status = Reservation.Status.NO_SHOW if action == "no_show" else Reservation.Status.CANCELLED
    else:
        fail("Unknown action.")
    r.save()
    log(request.user, f"Reservation {r.get_status_display().lower()}", f"{r.name}, {r.party_size}", r.location)
    return Response(ReservationSerializer(r).data)


# ---------- waitlist ----------

class WaitSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    waited_minutes = serializers.FloatField(read_only=True)
    minutes_so_far = serializers.SerializerMethodField()

    class Meta:
        model = WaitlistEntry
        fields = ["id", "location", "guest", "name", "phone", "party_size", "quoted_minutes", "status", "status_label",
                  "notes", "added_at", "notified_at", "seated_at", "left_at", "waited_minutes", "minutes_so_far"]
        read_only_fields = ["status", "added_at", "notified_at", "seated_at", "left_at"]

    def get_minutes_so_far(self, w):
        return round((timezone.now() - w.added_at).total_seconds() / 60, 1)


class Waitlist(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        today = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
        qs = WaitlistEntry.objects.filter(location=location, added_at__gte=today)
        active = qs.filter(status__in=[WaitlistEntry.Status.WAITING, WaitlistEntry.Status.NOTIFIED])
        seated = [w.waited_minutes for w in qs.filter(status=WaitlistEntry.Status.SEATED)]
        return Response({
            "waiting": WaitSerializer(active, many=True).data,
            "done": WaitSerializer(qs.exclude(id__in=active.values("id")).order_by("-added_at")[:30], many=True).data,
            "today": {"seated": len(seated), "avg_wait": sum(seated) / len(seated) if seated else None},
        })

    def post(self, request):
        s = WaitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        w = s.save(added_at=timezone.now(), created_by=request.user)
        log(request.user, "Added to waitlist", f"{w.name}, {w.party_size}, quoted {w.quoted_minutes} min", w.location)
        return Response(WaitSerializer(w).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsCook])
def waitlist_action(request, pk, action):
    w = get_object_or_404(WaitlistEntry.objects.select_related("location"), pk=pk)
    require_location(request.user, w.location)
    now = timezone.now()
    if action == "notify":
        if w.phone:
            messaging.send(w.location, w.phone, f"Hi {w.name}, your table at {w.location.name} is ready. Please come to the host stand.")
        w.status, w.notified_at = WaitlistEntry.Status.NOTIFIED, now
    elif action == "seat":
        order = _seat(request, w.location, request.data.get("table"), w.party_size, w.name, w.guest, w.phone)
        w.status, w.seated_at, w.table = WaitlistEntry.Status.SEATED, now, order.table
        w.save()
        return Response({**WaitSerializer(w).data, "order": order.id})
    elif action == "left":
        w.status, w.left_at = WaitlistEntry.Status.LEFT, now
    else:
        fail("Unknown action.")
    w.save()
    return Response(WaitSerializer(w).data)
