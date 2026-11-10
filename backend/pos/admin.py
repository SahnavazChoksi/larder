from django.contrib import admin

from .models import Order, OrderLine, Payment, Table, Ticket


class LineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("provider", "method", "amount", "tip", "status", "provider_ref", "refunded_amount", "approved_at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "type", "channel", "status", "table", "total", "opened_at", "closed_at")
    list_filter = ("location", "status", "type", "channel")
    inlines = [LineInline, PaymentInline]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "area", "seats", "x", "y", "is_active")
    list_filter = ("location",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "order", "status", "sent_at", "ready_at", "served_at")
    list_filter = ("location", "status")
