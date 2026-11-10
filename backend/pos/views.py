import hmac
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import (
    IsCook,
    IsManager,
    location_from_request,
    require_location,
)
from audit.services import log
from catalog.menu import menu_payload
from catalog.models import Location, MenuItem
from stock.services import fail

from . import payments as providers
from . import services
from .models import Order, OrderLine, Payment, Table, Ticket
from .serializers import (
    OrderBriefSerializer,
    OrderSerializer,
    PaymentSerializer,
    TableSerializer,
    TicketSerializer,
)

OPEN = Order.Status.OPEN


def _dec(value, field, default=None):
    if value in (None, ""):
        if default is None:
            fail(f"Enter {field}.")
        return default
    try:
        return Decimal(str(value))
    except InvalidOperation:
        fail(f"{field.capitalize()} must be a number.")


def _int(value, field, default=None):
    if value in (None, ""):
        if default is None:
            fail(f"Enter {field}.")
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        fail(f"{field.capitalize()} must be a whole number.")


def _order_qs():
    return Order.objects.select_related("location", "table", "server", "guest").prefetch_related(
        Prefetch("lines", queryset=OrderLine.objects.select_related("menu_item")), "payments", "tickets")


def _order(request, pk) -> Order:
    order = get_object_or_404(_order_qs(), pk=pk)
    require_location(request.user, order.location)
    return order


def _out(order, code=200):
    return Response(OrderSerializer(_order_qs().get(pk=order.pk)).data, status=code)


# ---------- menu for order taking (prices only, no costs) ----------

@api_view(["GET"])
@permission_classes([IsCook])
def menu(request):
    return Response(menu_payload(request))


# ---------- offline mode ----------

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def ping(request):
    """Tablets poll this to know whether the server is reachable."""
    return Response({"ok": True, "time": timezone.now()})


@api_view(["GET"])
@permission_classes([IsCook])
def offline_kit(request):
    """Everything a tablet needs to keep taking orders if the connection drops: menu, tables, tax rules."""
    location = location_from_request(request)
    if location.kind != Location.Kind.OUTLET:
        fail("Only outlets take orders.")
    return Response({
        "location": {"id": location.id, "code": location.code, "name": location.name, "tax_rate": float(location.tax_rate),
                     "service_charge_rate": float(location.service_charge_rate),
                     "service_charge_party": location.service_charge_party},
        "tables": TableSerializer(Table.objects.filter(location=location, is_active=True), many=True).data,
        "menu": menu_payload(request),
        "saved_at": timezone.now(),
    })


def _when(value, field):
    at = parse_datetime(str(value or ""))
    if not at:
        fail(f"{field} is missing or not a date and time.")
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    now = timezone.now()
    if at > now + timedelta(minutes=10) or at < now - timedelta(days=7):
        fail(f"{field} is out of range: offline orders must be from the last 7 days.")
    return at


def _offline_order(raw) -> dict:
    """Validate one order from a tablet's outbox."""
    if not isinstance(raw, dict):
        fail("Each order must be an object.")
    client_id = str(raw.get("client_id", "")).strip()
    if not 8 <= len(client_id) <= 64:
        fail("client_id is missing.")
    if raw.get("type") not in (Order.Type.DINE_IN, Order.Type.TAKEOUT):
        fail("Offline orders are dine-in or takeout.")
    lines = raw.get("lines") or []
    if not isinstance(lines, list) or not 1 <= len(lines) <= 60:
        fail("An offline order needs between 1 and 60 items.")
    d = {"client_id": client_id, "type": raw["type"], "table": raw.get("table") or None,
         "guests": max(1, min(_int(raw.get("guests"), "guests", 1), 40)),
         "customer_name": str(raw.get("customer_name", ""))[:100],
         "opened_at": _when(raw.get("opened_at"), "opened_at"),
         "closed_at": _when(raw["closed_at"], "closed_at") if raw.get("closed_at") else None, "lines": [], "payments": []}
    for x in lines:
        if not isinstance(x, dict):
            fail("Each item must be an object.")
        mods = x.get("modifiers") or []
        if not isinstance(mods, list):
            fail("modifiers should be a list of option ids.")
        d["lines"].append({"menu_item": _int(x.get("menu_item"), "dish"), "qty": _int(x.get("qty"), "quantity", 1),
                           "price": _dec(x.get("price"), "price"), "modifiers": [_int(m, "option") for m in mods],
                           "note": str(x.get("note", ""))[:120],
                           "sent_at": _when(x["sent_at"], "sent_at") if x.get("sent_at") else None})
        if d["lines"][-1]["price"] < 0:
            fail("A price can't be negative.")
    for p in raw.get("payments") or []:
        if not isinstance(p, dict):
            fail("Each payment must be an object.")
        if p.get("method") not in (Payment.Method.CASH, Payment.Method.CARD, Payment.Method.GIFT, Payment.Method.OTHER):
            fail("Unknown payment method.")
        d["payments"].append({"method": p["method"], "amount": _dec(p.get("amount"), "amount"), "tip": _dec(p.get("tip"), "tip", Decimal(0)),
                              "cash_tendered": _dec(p["cash_tendered"], "cash given") if p.get("cash_tendered") not in (None, "") else None,
                              "reference": str(p.get("reference", ""))[:60]})
    return d


@api_view(["POST"])
@permission_classes([IsCook])
def offline_orders(request):
    """Upload orders a tablet took while offline. Each one is booked on its own; uploading twice is harmless.

    Body: {"location": id, "device": "Front tablet", "orders": [{client_id, type, table, guests, customer_name,
    opened_at, closed_at, lines: [{menu_item, qty, price, modifiers, note, sent_at}],
    payments: [{method, amount, tip, cash_tendered, reference}]}]}
    """
    location = location_from_request(request)
    orders = request.data.get("orders")
    if not isinstance(orders, list) or not 1 <= len(orders) <= 50:
        fail("Send between 1 and 50 orders at a time.")
    device = str(request.data.get("device", ""))[:40]
    results = []
    for raw in orders:
        cid = str(raw.get("client_id", "")) if isinstance(raw, dict) else ""
        try:
            with transaction.atomic():
                order, outcome = services.import_offline_order(location, request.user, _offline_order(raw), device)
        except ValidationError as exc:
            results.append({"client_id": cid, "status": "error", "message": " ".join(_messages(exc.detail))})
            continue
        if outcome != "duplicate":
            log(request.user, "Synced offline order", f"{order.number}, ${order.total}"
                + ("" if outcome == "closed" else ", left open for a manager"), location)
        results.append({"client_id": cid, "status": outcome, "order": order.id, "number": order.number,
                        "total": float(order.total), "balance": float(order.balance())})
    return Response({"results": results})


def _messages(detail):
    if isinstance(detail, dict):
        return [m for v in detail.values() for m in _messages(v)]
    if isinstance(detail, list):
        return [m for v in detail for m in _messages(v)]
    return [str(detail)]


# ---------- floor plan and tables ----------

@api_view(["GET"])
@permission_classes([IsCook])
def floor(request):
    location = location_from_request(request)
    open_orders = list(Order.objects.filter(location=location, status=OPEN).select_related("table", "server")
                       .prefetch_related("tickets"))
    by_table = {o.table_id: o for o in open_orders if o.table_id}
    tables = []
    for t in Table.objects.filter(location=location, is_active=True):
        o = by_table.get(t.id)
        tables.append({**TableSerializer(t).data, "order": None if not o else {
            **OrderBriefSerializer(o).data,
            "food_ready": any(k.status == Ticket.Status.READY for k in o.tickets.all()),
            "waiting_kitchen": any(k.status in (Ticket.Status.NEW, Ticket.Status.STARTED) for k in o.tickets.all()),
        }})
    others = [o for o in open_orders if not o.table_id]
    return Response({"tables": tables, "orders": OrderBriefSerializer(others, many=True).data,
                     "providers": [p.describe() for p in providers.enabled()],
                     "tax_rate": float(location.tax_rate)})


class Tables(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "POST" else [IsCook()]

    def get(self, request):
        location = location_from_request(request)
        return Response(TableSerializer(Table.objects.filter(location=location), many=True).data)

    def post(self, request):
        s = TableSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        require_location(request.user, s.validated_data["location"])
        t = s.save()
        log(request.user, "Added table", f"{t.name}, {t.seats} seats", t.location)
        return Response(TableSerializer(t).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsManager])
def table_detail(request, pk):
    t = get_object_or_404(Table, pk=pk)
    require_location(request.user, t.location)
    s = TableSerializer(t, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    t = s.save()
    log(request.user, "Changed table", t.name, t.location)
    return Response(TableSerializer(t).data)


# ---------- orders ----------

class Orders(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        qs = Order.objects.filter(location=location).select_related("table", "server")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("date"):
            qs = qs.filter(business_date=p["date"])
        return Response(OrderBriefSerializer(qs[:200], many=True).data)

    def post(self, request):
        from guests.models import Guest

        location = location_from_request(request)
        d = request.data
        table = get_object_or_404(Table, pk=d["table"]) if d.get("table") else None
        guest = get_object_or_404(Guest, pk=d["guest"]) if d.get("guest") else None
        order_type = d.get("type") or (Order.Type.DINE_IN if table else Order.Type.TAKEOUT)
        if order_type not in Order.Type.values:
            fail("Unknown order type.")
        order = services.open_order(location, request.user, type=order_type, table=table,
                                    guests=_int(d.get("guests"), "guests", 1), guest=guest,
                                    customer_name=d.get("customer_name", ""), customer_phone=d.get("customer_phone", ""),
                                    note=d.get("note", ""))
        log(request.user, "Opened order", f"{order.number} {order.get_type_display()}" + (f" at {table.name}" if table else ""), location)
        return _out(order, status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsCook])
def order_detail(request, pk):
    from guests.models import Guest

    order = _order(request, pk)
    if request.method == "PATCH":
        d = request.data
        if "guests" in d:
            services.set_guests(order, _int(d["guests"], "guests"))
        if "guest" in d:
            services._require_open(order)
            order.guest = get_object_or_404(Guest, pk=d["guest"]) if d["guest"] else None
            if order.guest and not order.customer_name:
                order.customer_name = order.guest.name
            order.save(update_fields=["guest", "customer_name"])
        if "note" in d:
            order.note = str(d["note"])[:300]
            order.save(update_fields=["note"])
        if "table" in d and d["table"]:
            services._require_open(order)
            table = get_object_or_404(Table, pk=d["table"], location=order.location)
            if Order.objects.filter(table=table, status=OPEN).exclude(pk=order.pk).exists():
                fail(f"{table.name} already has an open check.")
            order.table = table
            order.save(update_fields=["table"])
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def add_line(request, pk):
    order = _order(request, pk)
    item = get_object_or_404(MenuItem, pk=request.data.get("menu_item"))
    seat = request.data.get("seat")
    mods = request.data.get("modifiers") or []
    if not isinstance(mods, list):
        fail("modifiers should be a list of option ids.")
    services.add_line(order, item, _int(request.data.get("qty"), "quantity", 1), request.user,
                      note=request.data.get("note", ""), seat=_int(seat, "seat") if seat not in (None, "") else None,
                      modifiers=[_int(m, "option") for m in mods])
    return _out(order, status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsCook])
def change_line(request, pk, line_id):
    order = _order(request, pk)
    line = get_object_or_404(OrderLine, pk=line_id, order=order)
    services.change_line(line, qty=_int(request.data["qty"], "quantity") if "qty" in request.data else None,
                         note=request.data.get("note"))
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def void_line(request, pk, line_id):
    order = _order(request, pk)
    line = get_object_or_404(OrderLine, pk=line_id, order=order)
    if line.status == OrderLine.Status.SENT and not request.user.has_role("manager"):
        fail("A manager has to void items the kitchen already has.")
    reason = request.data.get("reason", "")
    services.void_line(line, reason, request.user)
    if line.status == OrderLine.Status.VOID and line.ticket_id:
        log(request.user, "Voided item", f"{order.number}: {line.qty}× {line.name} ({reason})", order.location)
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def send(request, pk):
    order = _order(request, pk)
    services.send_to_kitchen(order, request.user, rush=bool(request.data.get("rush")))
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def service_charge(request, pk):
    """Servers can remove the service charge when a guest asks; it's counted on the SC removed % report."""
    order = _order(request, pk)
    reason = request.data.get("reason", "")
    services.remove_service_charge(order, reason)
    log(request.user, "Removed service charge", f"{order.number}: {reason}", order.location)
    return _out(order)


@api_view(["POST"])
@permission_classes([IsManager])
def discount(request, pk):
    order = _order(request, pk)
    amount = _dec(request.data.get("amount"), "the discount")
    reason = request.data.get("reason", "")
    services.apply_discount(order, amount, reason)
    log(request.user, "Gave discount", f"{order.number}: ${amount} ({reason})", order.location)
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def redeem(request, pk):
    order = _order(request, pk)
    services.redeem_points(order, _int(request.data.get("rewards"), "rewards", 1), request.user)
    return _out(order)


@api_view(["POST"])
@permission_classes([IsCook])
def pay(request, pk):
    order = _order(request, pk)
    d = request.data
    method = d.get("method", Payment.Method.CARD)
    if method not in Payment.Method.values:
        fail("Unknown payment method.")
    tendered = d.get("cash_tendered")
    payment, result = services.take_payment(
        order, request.user, provider=d.get("provider", "manual"), method=method,
        amount=_dec(d.get("amount"), "amount", default=order.balance()) if d.get("amount") not in (None, "") else None,
        tip=_dec(d.get("tip"), "tip", Decimal(0)),
        cash_tendered=_dec(tendered, "cash tendered") if tendered not in (None, "") else None,
        reference=str(d.get("reference", "")),
    )
    log(request.user, "Took payment", f"{order.number}: ${payment.amount} {payment.get_method_display()}"
        + (f" + ${payment.tip} tip" if payment.tip else "") + f" ({payment.get_status_display()})", order.location)
    order = _order_qs().get(pk=order.pk)
    closed = False
    if payment.status == Payment.Status.APPROVED and order.balance() <= 0 and d.get("auto_close", True):
        try:
            services.close_order(order, request.user)
            closed = True
        except Exception:
            closed = False  # e.g. unsent items; staff close manually after fixing
    data = OrderSerializer(_order_qs().get(pk=order.pk)).data
    return Response({"order": data, "payment": PaymentSerializer(payment).data, "closed": closed,
                     "client_action": result.client_action, "message": result.message}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsManager])
def refund(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("order__location"), pk=pk)
    require_location(request.user, payment.order.location)
    amount = _dec(request.data.get("amount"), "the refund amount")
    services.refund(payment, amount, request.user)
    log(request.user, "Refunded payment", f"{payment.order.number}: ${amount} {payment.get_method_display()}", payment.order.location)
    return Response(PaymentSerializer(payment).data)


@api_view(["POST"])
@permission_classes([IsCook])
def close(request, pk):
    order = _order(request, pk)
    services.close_order(order, request.user)
    log(request.user, "Closed order", f"{order.number} ${order.total}", order.location)
    return _out(order)


@api_view(["POST"])
@permission_classes([IsManager])
def void(request, pk):
    order = _order(request, pk)
    reason = request.data.get("reason", "")
    services.void_order(order, reason, request.user)
    log(request.user, "Voided order", f"{order.number}: {reason}", order.location)
    return _out(order)


# ---------- kitchen display ----------

@api_view(["GET"])
@permission_classes([IsCook])
def kds(request):
    """view=kitchen: tickets to cook. view=expo: tickets ready to run to tables."""
    location = location_from_request(request)
    view = request.query_params.get("view", "kitchen")
    statuses = [Ticket.Status.READY] if view == "expo" else [Ticket.Status.NEW, Ticket.Status.STARTED]
    qs = Ticket.objects.filter(location=location, status__in=statuses) \
        .select_related("order__table", "order__server", "order__guest").prefetch_related("lines").order_by("-is_rush", "sent_at")
    today = timezone.localdate()
    done = Ticket.objects.filter(location=location, ready_at__date=today)
    times = [t.prep_minutes for t in done if t.prep_minutes is not None]
    return Response({
        "tickets": TicketSerializer(qs[:60], many=True).data,
        "target_minutes": settings.TICKET_TARGET_MINUTES,
        "today": {"done": len(times), "avg_prep": sum(times) / len(times) if times else None,
                  "late": sum(1 for m in times if m > settings.TICKET_TARGET_MINUTES)},
    })


@api_view(["POST"])
@permission_classes([IsCook])
def ticket_step(request, pk, step):
    ticket = get_object_or_404(Ticket.objects.select_related("order", "location"), pk=pk)
    require_location(request.user, ticket.location)
    services.ticket_step(ticket, step)
    return Response(TicketSerializer(ticket).data)


# ---------- payment providers, webhooks, integrations ----------

@api_view(["GET"])
@permission_classes([IsCook])
def provider_list(request):
    return Response([p.describe() for p in providers.enabled()])


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_webhook(request, provider):
    """Processors call this when a card payment finishes. Each provider verifies its own signature."""
    try:
        payment = providers.get(provider).handle_webhook(request)
    except providers.PaymentError as exc:
        return Response({"detail": str(exc)}, status=400)
    if payment and payment.status == Payment.Status.APPROVED:
        order = payment.order
        if order.status == OPEN and order.balance() <= 0:
            services.close_order(order, None)
    return Response({"ok": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def integration_order(request, platform):
    """Delivery-app orders pushed by an adapter (or a middleware such as Otter/Deliverect).

    Header  X-Larder-Secret: <LARDER_INTEGRATION_SECRET>
    Body    {"location": "SQ1", "external_ref": "UE-123", "customer_name": "...", "note": "...",
             "lines": [{"pos_code": "SB01", "qty": 2, "price": 13.45, "note": "no pickles"}]}
    The order goes straight to the kitchen and is marked paid on the app.
    """
    secret = settings.LARDER_INTEGRATION_SECRET
    if not secret or not hmac.compare_digest(request.headers.get("X-Larder-Secret", ""), secret):
        return Response({"detail": "Not authorised."}, status=401)
    if platform not in ("uber_eats", "doordash", "skip", "other"):
        return Response({"detail": "Unknown platform."}, status=400)
    d = request.data
    location = get_object_or_404(Location, code=str(d.get("location", "")).upper())
    if Order.objects.filter(channel=platform, external_ref=d.get("external_ref", "")).exclude(external_ref="").exists():
        return Response({"detail": "Already received."}, status=200)
    menu = {m.pos_code: m for m in MenuItem.objects.filter(pos_code__in=[x.get("pos_code") for x in d.get("lines", [])])}
    missing = [x.get("pos_code") for x in d.get("lines", []) if x.get("pos_code") not in menu]
    if missing or not d.get("lines"):
        return Response({"detail": f"Unknown or missing items: {missing}"}, status=400)
    order = services.open_order(location, None, type=Order.Type.DELIVERY, channel=platform,
                                external_ref=str(d.get("external_ref", ""))[:80], customer_name=str(d.get("customer_name", ""))[:100],
                                note=str(d.get("note", ""))[:300])
    for x in d["lines"]:
        price = _dec(x.get("price"), "price", menu[x["pos_code"]].price)
        services.add_line(order, menu[x["pos_code"]], _int(x.get("qty"), "quantity", 1), None, note=str(x.get("note", "")), price=price,
                          default_modifiers=True)
    services.send_to_kitchen(order, None)
    services.take_payment(order, None, method=Payment.Method.APP, reference=order.external_ref)
    services.close_order(_order_qs().get(pk=order.pk), None)
    return Response({"order": order.id, "number": order.number}, status=201)


# ---------- public online ordering (no login) ----------

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def public_menu(request, code):
    location = get_object_or_404(Location, code=code.upper(), kind=Location.Kind.OUTLET)
    if not location.accepts_online_orders:
        return Response({"detail": f"{location.name} isn't taking online orders right now."}, status=404)
    return Response({
        "location": {"code": location.code, "name": location.name, "city": location.city, "tax_rate": float(location.tax_rate)},
        **menu_payload(request, public=True),
    })


public_menu.cls.throttle_scope = "public_menu"


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def public_order(request, code):
    """Pickup order from the website. Paid at pickup for now; a provider can add online card payment later."""
    location = get_object_or_404(Location, code=code.upper(), kind=Location.Kind.OUTLET, accepts_online_orders=True)
    d = request.data
    name, phone = str(d.get("name", "")).strip()[:100], str(d.get("phone", "")).strip()[:30]
    if not name or len(phone) < 7:
        fail("Enter your name and a phone number so we can reach you.")
    lines = d.get("lines") or []
    if not 1 <= len(lines) <= 30:
        fail("Add between 1 and 30 items.")
    menu = {m.id: m for m in MenuItem.objects.filter(is_active=True, id__in=[x.get("menu_item") for x in lines])}
    order = services.open_order(location, None, type=Order.Type.ONLINE, channel="website", customer_name=name,
                                customer_phone=phone, note=str(d.get("note", ""))[:300])
    for x in lines:
        item = menu.get(x.get("menu_item"))
        qty = _int(x.get("qty"), "quantity", 1)
        if not item or not 1 <= qty <= 20:
            fail("One of the items is unavailable or has a wrong quantity.")
        mods = x.get("modifiers") or []
        if not isinstance(mods, list):
            fail("modifiers should be a list of option ids.")
        services.add_line(order, item, qty, None, note=str(x.get("note", ""))[:120], modifiers=[_int(m, "option") for m in mods])
    services.send_to_kitchen(order, None)
    order.refresh_from_db()
    log(None, "Online order received", f"{order.number} {name}, ${order.total}", location)
    return Response({"number": order.number, "token": str(order.public_token), "total": float(order.total),
                     "estimate_minutes": settings.TICKET_TARGET_MINUTES + 5}, status=201)


public_order.cls.throttle_scope = "public_orders"


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def public_status(request, token):
    order = get_object_or_404(Order.objects.prefetch_related("tickets", "lines"), public_token=token)
    tickets = list(order.tickets.all())
    state = "received"
    if tickets and all(t.status in (Ticket.Status.READY, Ticket.Status.SERVED) for t in tickets):
        state = "ready"
    elif any(t.status == Ticket.Status.STARTED for t in tickets):
        state = "cooking"
    if order.status == Order.Status.VOID:
        state = "cancelled"
    if order.status == Order.Status.CLOSED:
        state = "picked_up"
    return Response({"number": order.number, "state": state, "total": float(order.total), "location": order.location.name,
                     "items": [{"name": line.display_name, "qty": line.qty} for line in order.lines.exclude(status=OrderLine.Status.VOID)]})
