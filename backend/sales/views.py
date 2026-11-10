from datetime import date

from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsManager, location_from_request
from audit.services import log
from stock.services import fail

from . import services
from .models import SalesDay, SalesLine


def _date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        fail(f"{field} must be a date like 2026-11-08.")


@api_view(["GET"])
@permission_classes([IsManager])
def days(request):
    qs = SalesDay.objects.filter(location_id__in=request.user.location_ids()).select_related("location", "imported_by")
    location = location_from_request(request, required=False)
    if location:
        qs = qs.filter(location=location)
    p = request.query_params
    if p.get("start"):
        qs = qs.filter(business_date__gte=_date(p["start"], "start"))
    if p.get("end"):
        qs = qs.filter(business_date__lte=_date(p["end"], "end"))
    qs = qs.annotate(net=Sum("lines__net_sales"), portions=Sum("lines__qty"), dishes=Count("lines"))[:120]
    return Response([{
        "id": d.id, "location": d.location_id, "location_name": d.location.name, "business_date": d.business_date,
        "source": d.source, "net_sales": float(d.net or 0), "portions": d.portions or 0, "dishes": d.dishes,
        "covers": d.covers, "bills": d.bills, "sc_bills": d.sc_bills, "sc_removed": d.sc_removed, "is_history": d.is_history,
        "imported_by": d.imported_by.display_name if d.imported_by else None, "imported_at": d.imported_at,
    } for d in qs])


@api_view(["GET"])
@permission_classes([IsManager])
def item_sales(request):
    """Portions and revenue per dish for a location (or all of yours) over a date range."""
    p = request.query_params
    start, end = _date(p.get("start"), "start"), _date(p.get("end"), "end")
    qs = SalesLine.objects.filter(day__location_id__in=request.user.location_ids(),
                                  day__business_date__gte=start, day__business_date__lte=end)
    location = location_from_request(request, required=False)
    if location:
        qs = qs.filter(day__location=location)
    rows = qs.values("menu_item", "menu_item__name", "menu_item__category").order_by().annotate(
        qty=Sum("qty"), net=Sum("net_sales"))
    return Response(sorted(({
        "menu_item": r["menu_item"], "name": r["menu_item__name"], "category": r["menu_item__category"],
        "qty": r["qty"], "net_sales": float(r["net"]),
    } for r in rows), key=lambda r: -r["net_sales"]))


@api_view(["POST"])
@permission_classes([IsManager])
@parser_classes([MultiPartParser])
def import_csv(request):
    upload = request.FILES.get("file")
    if not upload:
        fail("Attach a CSV file in the 'file' field.")
    if upload.size > 20 * 1024 * 1024:
        fail("That file is over 20 MB. Split it into smaller exports.")
    history = str(request.data.get("history", "")).lower() in ("1", "true", "yes")
    kind, days = services.import_csv(upload.read(), request.user, request.user.location_ids(), history=history)
    label = {"items": "item sales", "summary": "covers and bills"}[kind]
    log(request.user, "Imported sales", f"{upload.name}: {days} location-days of {label}" + (" (history, no stock usage)" if history else ""))
    return Response({"kind": kind, "days": days}, status=status.HTTP_201_CREATED)
