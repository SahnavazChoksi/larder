from decimal import Decimal

from rest_framework import serializers

from catalog.models import Item, Location

from .models import Movement, ProductionBatch, StockCount, Transfer, Wastage

POSITIVE = Decimal("0.0001")


def _name(user):
    return user.display_name if user else None


# ---------- input ----------

class ItemQtyIn(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))


class ParIn(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    par = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"), allow_null=True)


class ParsIn(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    pars = ParIn(many=True)


class CountIn(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    counted_on = serializers.DateField(required=False)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lines = ItemQtyIn(many=True)


class WastageIn(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=POSITIVE)
    reason = serializers.ChoiceField(choices=Wastage.Reason.choices)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    occurred_on = serializers.DateField(required=False)


class TransferIn(serializers.Serializer):
    from_location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    to_location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lines = ItemQtyIn(many=True)


class LineQtyIn(serializers.Serializer):
    id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))


class LineQtysIn(serializers.Serializer):
    lines = LineQtyIn(many=True, required=False, default=list)


class BatchIn(serializers.Serializer):
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.filter(kind=Location.Kind.KITCHEN))
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.filter(kind=Item.Kind.PREP))
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    planned_for = serializers.DateField(required=False)


class BatchQtyIn(serializers.Serializer):
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))


# ---------- output ----------

class MovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name")
    unit = serializers.CharField(source="item.unit")
    kind_label = serializers.CharField(source="get_kind_display")
    value = serializers.DecimalField(max_digits=16, decimal_places=2)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Movement
        fields = ["id", "occurred_on", "item", "item_name", "unit", "kind", "kind_label", "qty",
                  "unit_cost", "value", "reference", "created_by_name"]

    def get_created_by_name(self, m):
        return _name(m.created_by)


class CountSerializer(serializers.ModelSerializer):
    number = serializers.CharField()
    location_name = serializers.CharField(source="location.name")
    created_by_name = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(source="lines.count")

    class Meta:
        model = StockCount
        fields = ["id", "number", "location", "location_name", "counted_on", "note", "value_difference",
                  "item_count", "created_by_name", "created_at"]

    def get_created_by_name(self, c):
        return _name(c.created_by)


class WastageSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name")
    unit = serializers.CharField(source="item.unit")
    location_name = serializers.CharField(source="location.name")
    reason_label = serializers.CharField(source="get_reason_display")
    cost = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Wastage
        fields = ["id", "occurred_on", "location", "location_name", "item", "item_name", "unit", "qty",
                  "reason", "reason_label", "note", "cost", "created_by_name"]

    def get_cost(self, w):
        return float(w.qty * w.unit_cost)

    def get_created_by_name(self, w):
        return _name(w.created_by)


class TransferSerializer(serializers.ModelSerializer):
    number = serializers.CharField()
    from_name = serializers.CharField(source="from_location.name")
    to_name = serializers.CharField(source="to_location.name")
    status_label = serializers.CharField(source="get_status_display")
    lines = serializers.SerializerMethodField()
    value = serializers.SerializerMethodField()
    has_shortage = serializers.SerializerMethodField()
    requested_by_name = serializers.SerializerMethodField()
    received_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Transfer
        fields = ["id", "number", "from_location", "from_name", "to_location", "to_name", "status", "status_label",
                  "note", "requested_on", "dispatched_on", "received_on", "requested_by_name", "received_by_name",
                  "lines", "value", "has_shortage"]

    def get_lines(self, t):
        return [{
            "id": line.id, "item": line.item_id, "name": line.item.name, "unit": line.item.unit,
            "qty_requested": float(line.qty_requested),
            "qty_sent": float(line.qty_sent) if line.qty_sent is not None else None,
            "qty_received": float(line.qty_received) if line.qty_received is not None else None,
        } for line in t.lines.all()]

    def get_value(self, t):
        total = Decimal("0")
        for line in t.lines.all():
            qty = line.qty_sent if line.qty_sent is not None else line.qty_requested
            total += qty * (line.unit_cost if line.unit_cost is not None else line.item.unit_cost())
        return float(total)

    def get_has_shortage(self, t):
        return any(line.qty_received is not None and line.qty_received < line.qty_sent for line in t.lines.all())

    def get_requested_by_name(self, t):
        return _name(t.requested_by)

    def get_received_by_name(self, t):
        return _name(t.received_by)


class BatchSerializer(serializers.ModelSerializer):
    number = serializers.CharField()
    item_name = serializers.CharField(source="item.name")
    unit = serializers.CharField(source="item.unit")
    status_label = serializers.CharField(source="get_status_display")
    cost = serializers.SerializerMethodField()
    requirements = serializers.SerializerMethodField()

    class Meta:
        model = ProductionBatch
        fields = ["id", "number", "location", "item", "item_name", "unit", "qty", "status", "status_label",
                  "planned_for", "completed_on", "cost", "requirements"]

    def get_cost(self, b):
        return float(b.item.unit_cost() * b.qty)

    def get_requirements(self, b):
        stock = self.context.get("stock", {})
        return [{
            "item": item.id, "name": item.name, "unit": item.unit, "need": float(qty),
            "have": float(stock.get(item.id, 0)),
        } for item, qty in self.context["requirements"](b)]
