from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCook, IsManager, location_from_request, require_location
from audit.services import log
from catalog.models import Item, Location, Vendor
from stock.services import fail

from . import services
from .models import PurchaseOrder


# ---------- serializers ----------

class LineIn(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(kind=Item.Kind.RAW))
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal("0"), required=False, allow_null=True)


class OrderIn(serializers.Serializer):
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all())
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lines = LineIn(many=True)


class ReceiveLineIn(serializers.Serializer):
    id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal("0"), required=False, allow_null=True)


class ReceiveIn(serializers.Serializer):
    invoice_number = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    lines = ReceiveLineIn(many=True, required=False, default=list)


class PickIn(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(kind=Item.Kind.RAW))
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0.0001"))


class SuggestionsIn(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    lines = PickIn(many=True)


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.CharField()
    vendor_name = serializers.CharField(source="vendor.name")
    location_name = serializers.CharField(source="location.name")
    status_label = serializers.CharField(source="get_status_display")
    source_label = serializers.CharField(source="get_source_display")
    total = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ["id", "number", "vendor", "vendor_name", "location", "location_name", "status", "status_label",
                  "source", "source_label", "note", "invoice_number", "created_on", "expected_on", "sent_on",
                  "received_on", "created_by_name", "total", "lines"]

    def get_total(self, o):
        return float(o.total())

    def get_created_by_name(self, o):
        return o.created_by.display_name if o.created_by else None

    def get_lines(self, o):
        return [{
            "id": line.id, "item": line.item_id, "name": line.item.name, "unit": line.item.unit,
            "qty": float(line.qty), "unit_price": float(line.unit_price),
            "qty_received": float(line.qty_received) if line.qty_received is not None else None,
            "price_received": float(line.price_received) if line.price_received is not None else None,
        } for line in o.lines.all()]


def _valid(cls, data):
    s = cls(data=data)
    s.is_valid(raise_exception=True)
    return s.validated_data


def _orders(user):
    return (PurchaseOrder.objects.filter(location_id__in=user.location_ids())
            .select_related("vendor", "location", "created_by").prefetch_related("lines__item"))


def _summary(order):
    return f"{order.number} {order.vendor.name} → {order.location.name}, ${order.total():,.2f}"


# ---------- views ----------

class Orders(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "POST" else [IsCook()]

    def get(self, request):
        qs = _orders(request.user)
        location = location_from_request(request, required=False)
        if location:
            qs = qs.filter(location=location)
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response(OrderSerializer(qs[:100], many=True).data)

    def post(self, request):
        data = _valid(OrderIn, request.data)
        require_location(request.user, data["location"])
        order = services.create_order(
            data["vendor"], data["location"],
            [(line["item"], line["qty"], line.get("unit_price")) for line in data["lines"]], request.user, note=data["note"],
        )
        log(request.user, "Created purchase order", _summary(order), order.location)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


def _get(request, pk):
    order = get_object_or_404(_orders(request.user), pk=pk)
    require_location(request.user, order.location)
    return order


@api_view(["POST"])
@permission_classes([IsManager])
def send_order(request, pk):
    order = _get(request, pk)
    services.send_order(order)
    log(request.user, "Sent purchase order", _summary(order), order.location)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsCook])
def receive_order(request, pk):
    """Anyone on shift can receive a delivery. Changing the price on receipt needs a manager."""
    order = _get(request, pk)
    data = _valid(ReceiveIn, request.data)
    received = {}
    for line in data["lines"]:
        price = line.get("unit_price")
        received[line["id"]] = (line["qty"], price)
    if any(p is not None for _, p in received.values()) and not request.user.has_role("manager"):
        ordered = {line.id: line.unit_price for line in order.lines.all()}
        if any(p is not None and p != ordered.get(i) for i, (_, p) in received.items()):
            fail("Only a manager can change prices when receiving. Receive the quantities and ask a manager to fix the price.")
    changes = services.receive_order(order, received, request.user, data["invoice_number"])
    order.refresh_from_db()
    detail = _summary(order) + (f". Price changes: {'; '.join(changes)}" if changes else "")
    log(request.user, "Received delivery", detail, order.location)
    return Response(OrderSerializer(_orders(request.user).get(pk=pk)).data)


@api_view(["POST"])
@permission_classes([IsManager])
def cancel_order(request, pk):
    order = _get(request, pk)
    if order.status not in (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.SENT):
        fail("Only draft or sent orders can be cancelled.")
    order.status = PurchaseOrder.Status.CANCELLED
    order.save(update_fields=["status"])
    log(request.user, "Cancelled purchase order", _summary(order), order.location)
    return Response(OrderSerializer(order).data)


class Suggestions(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        location = location_from_request(request)
        return Response(services.reorder_suggestions(location))

    def post(self, request):
        data = _valid(SuggestionsIn, request.data)
        require_location(request.user, data["location"])
        orders = services.orders_from_suggestions(data["location"], [(p["item"], p["qty"]) for p in data["lines"]], request.user)
        for order in orders:
            log(request.user, "Created purchase order", _summary(order) + " (from reorder suggestions)", order.location)
        return Response(OrderSerializer(orders, many=True).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsManager])
def price_moves(request):
    return Response(services.recent_price_moves(int(request.query_params.get("days", 14))))



# ---------- invoice scanning ----------

from rest_framework.parsers import FormParser, MultiPartParser  # noqa: E402

from . import invoices  # noqa: E402
from .models import InvoiceScan  # noqa: E402


class ScanSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    file_url = serializers.SerializerMethodField()
    is_pdf = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="order.number", read_only=True, default=None)
    total = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceScan
        fields = ["id", "number", "location", "location_name", "vendor", "vendor_name", "vendor_text", "status",
                  "status_label", "invoice_number", "invoice_date", "lines", "engine", "message", "file_url", "is_pdf",
                  "order", "order_number", "created_at", "total"]
        read_only_fields = ["location", "status", "engine", "message", "order", "vendor_text"]

    def get_file_url(self, s):
        return s.file.url if s.file else None

    def get_is_pdf(self, s):
        return s.file.name.lower().endswith(".pdf") if s.file else False

    def get_total(self, s):
        return round(sum((x.get("qty") or 0) * (x.get("unit_price") or 0) for x in s.lines), 2)

    def validate_lines(self, lines):
        clean = []
        for x in lines:
            if not isinstance(x, dict):
                raise serializers.ValidationError("Each line must be an object.")
            clean.append({
                "text": str(x.get("text", ""))[:200], "unit_printed": str(x.get("unit_printed", ""))[:20],
                "item": int(x["item"]) if x.get("item") else None,
                "qty": float(x["qty"]) if x.get("qty") not in (None, "") else None,
                "unit_price": float(x["unit_price"]) if x.get("unit_price") not in (None, "") else None,
                "confidence": x.get("confidence", 100), "note": str(x.get("note", ""))[:120],
            })
        return clean


def _scan(request, pk):
    scan = get_object_or_404(InvoiceScan.objects.select_related("location", "vendor", "order"), pk=pk)
    require_location(request.user, scan.location)
    return scan


class Scans(APIView):
    permission_classes = [IsCook]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        qs = InvoiceScan.objects.filter(location_id__in=request.user.location_ids()).select_related("location", "vendor", "order")
        location = location_from_request(request, required=False)
        if location:
            qs = qs.filter(location=location)
        return Response(ScanSerializer(qs[:50], many=True).data)

    def post(self, request):
        """Multipart: file, location, optional vendor. Anyone receiving a delivery can scan."""
        location = location_from_request(request)
        upload = request.FILES.get("file")
        if not upload:
            fail("Attach a photo or PDF of the invoice.")
        vendor = Vendor.objects.filter(pk=request.data.get("vendor")).first() if request.data.get("vendor") else None
        scan = invoices.create_scan(location, upload, request.user, vendor)
        log(request.user, "Scanned invoice", f"{scan.number}: {scan.message}", location)
        return Response(ScanSerializer(scan).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsCook])
def scan_detail(request, pk):
    scan = _scan(request, pk)
    if request.method == "PATCH":
        if scan.status != InvoiceScan.Status.DRAFT:
            fail("Only drafts can be changed.")
        s = ScanSerializer(scan, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        scan = s.save()
    return Response(ScanSerializer(scan).data)


@api_view(["POST"])
@permission_classes([IsManager])
def scan_approve(request, pk):
    """Managers approve because approving can change ingredient prices."""
    scan = _scan(request, pk)
    order = invoices.approve(scan, request.user)
    changes = getattr(scan, "price_changes", [])
    log(request.user, "Approved scanned invoice",
        f"{scan.number} → {order.number}, ${order.total():,.2f}" + (f". Price changes: {'; '.join(changes)}" if changes else ""),
        scan.location)
    return Response(ScanSerializer(scan).data | {"price_changes": changes})


@api_view(["POST"])
@permission_classes([IsCook])
def scan_discard(request, pk):
    scan = _scan(request, pk)
    if scan.status != InvoiceScan.Status.DRAFT:
        fail("Only drafts can be discarded.")
    scan.status = InvoiceScan.Status.DISCARDED
    scan.save(update_fields=["status"])
    log(request.user, "Discarded invoice scan", scan.number, scan.location)
    return Response(ScanSerializer(scan).data)
