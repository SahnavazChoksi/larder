from django.contrib import admin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "location", "detail")
    list_filter = ("action", "location")
    search_fields = ("detail", "action")

    # Read-only in the admin too: the trail must not be edited.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
