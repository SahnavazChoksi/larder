from django.db.models import Q
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from accounts.models import Role
from accounts.permissions import IsManager

from .models import AuditEntry


class AuditEntrySerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_role = serializers.CharField(source="user.role", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)

    class Meta:
        model = AuditEntry
        fields = ["id", "created_at", "user", "user_name", "user_role", "action", "detail", "location", "location_name"]

    def get_user_name(self, entry):
        return entry.user.display_name if entry.user else "System"


class AuditPage(PageNumberPagination):
    page_size = 50


class AuditListView(ListAPIView):
    """Managers see entries for their locations (plus their own); owners see everything."""

    serializer_class = AuditEntrySerializer
    permission_classes = [IsManager]
    pagination_class = AuditPage

    def get_queryset(self):
        user = self.request.user
        qs = AuditEntry.objects.select_related("user", "location")
        if not (user.is_superuser or user.role == Role.OWNER):
            qs = qs.filter(Q(location_id__in=user.location_ids()) | Q(user=user))
        params = self.request.query_params
        if params.get("location"):
            qs = qs.filter(location_id=params["location"])
        if params.get("user"):
            qs = qs.filter(user_id=params["user"])
        if params.get("role"):
            qs = qs.filter(user__role=params["role"])
        if params.get("q"):
            qs = qs.filter(Q(action__icontains=params["q"]) | Q(detail__icontains=params["q"]))
        return qs
