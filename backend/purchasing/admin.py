from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine


class LineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "location", "status", "created_on", "received_on")
    list_filter = ("status", "vendor", "location")
    inlines = [LineInline]
