from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCook, IsManager, location_from_request, require_location
from audit.services import log
from catalog.models import Location

from . import services
from .models import Movement, ProductionBatch, StockCount, Transfer, Wastage
from .serializers import (
    BatchIn, BatchQtyIn, BatchSerializer, CountIn, CountSerializer, LineQtysIn, MovementSerializer, ParsIn,
    TransferIn, TransferSerializer, WastageIn, WastageSerializer,
)


class Page(PageNumberPagination):
    page_size = 50


def _valid(serializer_class, data):
    s = serializer_class(data=data)
    s.is_valid(raise_exception=True)
    return s.validated_data


# ---------- levels, pars, movements ----------

@api_view(["GET"])
def levels(request):
    location = location_from_request(request)
    return Response(services.stock_levels(location))


@api_view(["POST"])
@permission_classes([IsManager])
def set_pars(request):
    data = _valid(ParsIn, request.data)
    require_location(request.user, data["location"])
    changes = services.set_pars(data["location"], [(p["item"], p["par"]) for p in data["pars"]], request.user)
    if changes:
        log(request.user, "Changed par levels", "; ".join(changes), data["location"])
    return Response({"changed": len(changes)})


class MovementList(ListAPIView):
    serializer_class = MovementSerializer
    pagination_class = Page

    def get_queryset(self):
        location = location_from_request(self.request)
        qs = Movement.objects.filter(location=location).select_related("item", "created_by")
        p = self.request.query_params
        if p.get("item"):
            qs = qs.filter(item_id=p["item"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        return qs


# ---------- counts ----------

class Counts(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request)
        qs = StockCount.objects.filter(location=location).select_related("location", "created_by")[:30]
        return Response(CountSerializer(qs, many=True).data)

    def post(self, request):
        data = _valid(CountIn, request.data)
        require_location(request.user, data["location"])
        count = services.post_count(
            data["location"], [(line["item"], line["qty"]) for line in data["lines"]], request.user,
            data.get("counted_on"), data["note"],
        )
        log(request.user, "Saved stock count",
            f"{count.number}: {len(data['lines'])} items, difference ${count.value_difference:,.2f}", data["location"])
        return Response(CountSerializer(count).data, status=status.HTTP_201_CREATED)


# ---------- wastage ----------

class WastageView(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        location = location_from_request(request, required=False)
        qs = Wastage.objects.filter(location_id__in=request.user.location_ids())
        if location:
            qs = qs.filter(location=location)
        qs = qs.select_related("item", "location", "created_by")[:200]
        return Response(WastageSerializer(qs, many=True).data)

    def post(self, request):
        data = _valid(WastageIn, request.data)
        require_location(request.user, data["location"])
        entry = services.log_wastage(data["location"], data["item"], data["qty"], data["reason"], request.user,
                                     data["note"], data.get("occurred_on"))
        log(request.user, "Logged wastage",
            f"{services.fmt_qty(entry.qty, entry.item.unit)} {entry.item.name}, {entry.get_reason_display()}"
            + (f" ({entry.note})" if entry.note else ""), entry.location)
        return Response(WastageSerializer(entry).data, status=status.HTTP_201_CREATED)


# ---------- transfers ----------

def _transfer_qs(user):
    ids = user.location_ids()
    return (Transfer.objects.filter(Q(from_location_id__in=ids) | Q(to_location_id__in=ids))
            .select_related("from_location", "to_location", "requested_by", "received_by")
            .prefetch_related("lines__item"))


class Transfers(APIView):
    permission_classes = [IsCook]

    def get(self, request):
        qs = _transfer_qs(request.user)
        location = location_from_request(request, required=False)
        if location:
            qs = qs.filter(Q(from_location=location) | Q(to_location=location))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response(TransferSerializer(qs[:100], many=True).data)

    def post(self, request):
        data = _valid(TransferIn, request.data)
        # You request stock *for* a location you work at.
        require_location(request.user, data["to_location"])
        t = services.request_transfer(data["from_location"], data["to_location"],
                                      [(line["item"], line["qty"]) for line in data["lines"]], request.user, data["note"])
        log(request.user, "Requested transfer",
            f"{t.number} {t.from_location.name} → {t.to_location.name}: "
            + ", ".join(f"{line.item.name} {services.fmt_qty(line.qty_requested, line.item.unit)}" for line in t.lines.all()),
            t.to_location)
        return Response(TransferSerializer(t).data, status=status.HTTP_201_CREATED)


def _line_qtys(request):
    data = _valid(LineQtysIn, request.data)
    return {line["id"]: line["qty"] for line in data["lines"]}


@api_view(["POST"])
@permission_classes([IsCook])
def dispatch_transfer(request, pk):
    t = get_object_or_404(_transfer_qs(request.user), pk=pk)
    require_location(request.user, t.from_location)
    services.dispatch_transfer(t, _line_qtys(request), request.user)
    log(request.user, "Dispatched transfer", f"{t.number} to {t.to_location.name}", t.from_location)
    return Response(TransferSerializer(_transfer_qs(request.user).get(pk=pk)).data)


@api_view(["POST"])
@permission_classes([IsCook])
def receive_transfer(request, pk):
    t = get_object_or_404(_transfer_qs(request.user), pk=pk)
    require_location(request.user, t.to_location)
    short = services.receive_transfer(t, _line_qtys(request), request.user)
    log(request.user, "Received transfer",
        f"{t.number} from {t.from_location.name}" + (": " + "; ".join(short) if short else ", all in full"), t.to_location)
    return Response(TransferSerializer(_transfer_qs(request.user).get(pk=pk)).data)


@api_view(["POST"])
@permission_classes([IsManager])
def cancel_transfer(request, pk):
    t = get_object_or_404(_transfer_qs(request.user), pk=pk)
    if t.status != Transfer.Status.REQUESTED:
        raise ValidationError({"detail": "Only requests that haven't been dispatched can be cancelled."})
    t.status = Transfer.Status.CANCELLED
    t.save(update_fields=["status"])
    log(request.user, "Cancelled transfer", t.number, t.to_location)
    return Response(TransferSerializer(t).data)


# ---------- production (central kitchen) ----------

def _batch_data(batches, location):
    ctx = {"stock": services.on_hand_map(location), "requirements": services.batch_requirements}
    return BatchSerializer(batches, many=True, context=ctx).data


class Batches(APIView):
    def get_permissions(self):
        return [IsManager()] if self.request.method == "POST" else [IsCook()]

    def get(self, request):
        location = location_from_request(request)
        qs = ProductionBatch.objects.filter(location=location).select_related("item")
        planned = list(qs.filter(status=ProductionBatch.Status.PLANNED))
        done = list(qs.filter(status=ProductionBatch.Status.DONE)[:20])
        return Response({
            "planned": _batch_data(planned, location),
            "done": _batch_data(done, location),
            "demand": services.prep_demand(location) if location.kind == Location.Kind.KITCHEN else [],
        })

    def post(self, request):
        data = _valid(BatchIn, request.data)
        require_location(request.user, data["location"])
        b = ProductionBatch.objects.create(
            location=data["location"], item=data["item"], qty=data["qty"],
            planned_for=data.get("planned_for") or timezone.localdate(), created_by=request.user,
        )
        log(request.user, "Planned batch", f"{b.number}: {services.fmt_qty(b.qty, b.item.unit)} {b.item.name}", b.location)
        return Response({"id": b.id}, status=status.HTTP_201_CREATED)


def _batch(request, pk):
    b = get_object_or_404(ProductionBatch.objects.select_related("item", "location"), pk=pk)
    require_location(request.user, b.location)
    return b


@api_view(["PATCH", "DELETE"])
@permission_classes([IsManager])
def batch_detail(request, pk):
    b = _batch(request, pk)
    if b.status != ProductionBatch.Status.PLANNED:
        raise ValidationError({"detail": "Cooked batches can't be changed."})
    if request.method == "DELETE":
        log(request.user, "Removed planned batch", f"{b.number}: {services.fmt_qty(b.qty, b.item.unit)} {b.item.name}", b.location)
        b.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    new_qty = _valid(BatchQtyIn, request.data)["qty"]
    old = b.qty
    b.qty = new_qty
    b.save(update_fields=["qty"])
    log(request.user, "Changed batch quantity",
        f"{b.number} {b.item.name}: {services.fmt_qty(old, b.item.unit)} → {services.fmt_qty(new_qty, b.item.unit)}", b.location)
    return Response({"id": b.id, "qty": float(b.qty)})


@api_view(["POST"])
@permission_classes([IsCook])
def complete_batch(request, pk):
    b = _batch(request, pk)
    services.complete_batch(b, request.user)
    log(request.user, "Marked batch cooked", f"{b.number}: {services.fmt_qty(b.qty, b.item.unit)} {b.item.name}", b.location)
    return Response({"id": b.id, "status": b.status})
