from django.contrib import admin

from .models import SalesDay, SalesLine


class LineInline(admin.TabularInline):
    model = SalesLine
    extra = 0


@admin.register(SalesDay)
class SalesDayAdmin(admin.ModelAdmin):
    list_display = ("business_date", "location", "source", "imported_by")
    list_filter = ("location",)
    inlines = [LineInline]
