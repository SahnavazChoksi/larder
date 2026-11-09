from datetime import date, timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsManager, location_from_request
from stock.services import fail

from . import services


def _range(request, default_days=30):
    p = request.query_params
    try:
        end = date.fromisoformat(p["end"]) if p.get("end") else timezone.localdate()
        start = date.fromisoformat(p["start"]) if p.get("start") else end - timedelta(days=default_days - 1)
    except ValueError:
        fail("Dates must look like 2026-11-08.")
    if start > end:
        fail("The start date is after the end date.")
    if (end - start).days > 366:
        fail("Pick a range of a year or less.")
    return start, end


@api_view(["GET"])
@permission_classes([IsManager])
def variance(request):
    location = location_from_request(request)
    start, end = _range(request)
    return Response(services.variance(location, start, end))


@api_view(["GET"])
@permission_classes([IsManager])
def dashboard(request):
    location = location_from_request(request, required=False)
    start, end = _range(request)
    return Response(services.dashboard(request.user, start, end, location))
