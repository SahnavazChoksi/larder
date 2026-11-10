from django.utils import timezone
from rest_framework import serializers

from .models import Order, OrderLine, Payment, Table, Ticket


def _name(u):
    return u.display_name if u else None


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ["id", "location", "name", "area", "seats", "x", "y", "shape", "is_active"]

    def validate(self, data):
        if not 0 <= data.get("x", 0) <= 11 or not 0 <= data.get("y", 0) <= 7:
            raise serializers.ValidationError("Floor plan positions go from 0–11 across and 0–7 down.")
        return data


class LineSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    category = serializers.CharField(source="menu_item.category", read_only=True)

    class Meta:
        model = OrderLine
        fields = ["id", "menu_item", "name", "category", "qty", "unit_price", "modifiers", "note", "seat", "status",
                  "status_label", "void_reason", "ticket"]


class TicketSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.number", read_only=True)
    order_type = serializers.CharField(source="order.get_type_display", read_only=True)
    channel = serializers.CharField(source="order.channel", read_only=True)
    table = serializers.CharField(source="order.table.name", read_only=True, default=None)
    customer = serializers.CharField(source="order.customer_name", read_only=True)
    allergies = serializers.SerializerMethodField()
    guests = serializers.IntegerField(source="order.guests", read_only=True)
    server = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    elapsed_minutes = serializers.SerializerMethodField()
    prep_minutes = serializers.FloatField(read_only=True)

    class Meta:
        model = Ticket
        fields = ["id", "order", "order_number", "order_type", "channel", "table", "customer", "guests", "server", "allergies",
                  "status", "is_rush", "sent_at", "started_at", "ready_at", "served_at", "elapsed_minutes", "prep_minutes", "lines"]

    def get_server(self, t):
        return _name(t.order.server)

    def get_lines(self, t):
        return [{"id": line.id, "name": line.name, "qty": line.qty, "note": line.note, "seat": line.seat,
                 "modifiers": [m["name"] for m in line.modifiers], "void": line.status == OrderLine.Status.VOID}
                for line in t.lines.all()]

    def get_allergies(self, t):
        """The kitchen sees the guest's allergies on every ticket for that check."""
        g = t.order.guest
        return g.allergies if g and g.allergies else ""

    def get_elapsed_minutes(self, t):
        end = t.ready_at or timezone.now()
        return round((end - t.sent_at).total_seconds() / 60, 1)


class PaymentSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    change_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "provider", "method", "method_label", "amount", "tip", "cash_tendered", "change_due", "status",
                  "status_label", "provider_ref", "provider_data", "refunded_amount", "created_at", "approved_at"]


class OrderSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    table_name = serializers.CharField(source="table.name", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True)
    tax_rate = serializers.DecimalField(source="location.tax_rate", max_digits=5, decimal_places=4, read_only=True)
    server_name = serializers.SerializerMethodField()
    guest_profile = serializers.SerializerMethodField()
    lines = LineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    tickets = serializers.SerializerMethodField()
    paid = serializers.SerializerMethodField()
    tips = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "number", "location", "location_name", "table", "table_name", "type", "type_label", "channel",
                  "external_ref", "status", "status_label", "guests", "server_name", "guest", "guest_profile", "customer_name",
                  "customer_phone", "pickup_at", "note", "service_charge_rate", "service_charge_removed",
                  "service_charge_removed_reason", "discount", "discount_reason", "subtotal", "service_charge", "tax",
                  "tax_rate", "total", "paid", "tips", "balance", "opened_at", "first_sent_at", "closed_at",
                  "business_date", "void_reason", "lines", "payments", "tickets"]

    def get_server_name(self, o):
        return _name(o.server)

    def get_guest_profile(self, o):
        g = o.guest
        return {"id": g.id, "name": g.name, "points": g.points, "is_member": g.is_member, "allergies": g.allergies,
                "visits": g.visits, "notes": g.notes} if g else None

    def get_tickets(self, o):
        return [{"id": t.id, "status": t.status, "status_label": t.get_status_display(), "sent_at": t.sent_at,
                 "ready_at": t.ready_at, "served_at": t.served_at} for t in o.tickets.all()]

    def get_paid(self, o):
        return float(o.paid())

    def get_tips(self, o):
        return float(o.tips())

    def get_balance(self, o):
        return float(o.balance())


class OrderBriefSerializer(serializers.ModelSerializer):
    number = serializers.CharField(read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    table_name = serializers.CharField(source="table.name", read_only=True, default=None)
    server_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "number", "type", "type_label", "channel", "status", "status_label", "table", "table_name",
                  "guests", "customer_name", "total", "opened_at", "first_sent_at", "closed_at", "server_name", "pickup_at"]

    def get_server_name(self, o):
        return _name(o.server)
