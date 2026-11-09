from django.contrib import admin

from .models import Movement, ParLevel, ProductionBatch, StockCount, Transfer, Wastage


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("occurred_on", "location", "item", "kind", "qty", "unit_cost", "reference", "created_by")
    list_filter = ("kind", "location")
    search_fields = ("item__name", "reference")

    # The ledger is append-only: fix mistakes with a new movement (e.g. a count), not by editing.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ParLevel)
admin.site.register(StockCount)
admin.site.register(Wastage)
admin.site.register(Transfer)
admin.site.register(ProductionBatch)
