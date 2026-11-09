"""Role checks and location access helpers shared by every app."""
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission


def role_permission(min_role: str):
    class RolePermission(BasePermission):
        message = f"This needs the {min_role} role or higher."

        def has_permission(self, request, view):
            user = request.user
            return bool(user and user.is_authenticated and user.has_role(min_role))

    RolePermission.__name__ = f"Is{min_role.capitalize()}"
    return RolePermission


IsCook = role_permission("cook")
IsManager = role_permission("manager")
IsOwner = role_permission("owner")


def require_location(user, location):
    if location.id not in user.location_ids():
        raise PermissionDenied("You don't have access to this location.")


def location_from_request(request, required=True, field="location"):
    """Read ?location=<id> (or a body field) and check the user may use it."""
    from catalog.models import Location

    value = request.query_params.get(field) or (request.data.get(field) if hasattr(request, "data") else None)
    if not value:
        if required:
            raise ValidationError({field: "Choose a location."})
        return None
    location = get_object_or_404(Location, pk=value)
    require_location(request.user, location)
    return location
