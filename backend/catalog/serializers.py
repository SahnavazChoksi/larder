from decimal import Decimal

from rest_framework import serializers

from .models import Item, Location, MenuCategory, MenuItem, Modifier, ModifierGroup, PriceHistory, Vendor


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name", "city", "kind", "brand"]


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ["id", "name", "lead_days", "delivery_days", "email", "phone"]


class ItemSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)
    unit_cost = serializers.SerializerMethodField()
    recipe = serializers.SerializerMethodField()
    allergen_list = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            "id", "name", "category", "unit", "kind", "vendor", "vendor_name", "last_price", "unit_cost",
            "shelf_life_days", "batch_size", "allergens", "allergen_list", "is_active", "recipe",
        ]

    def get_unit_cost(self, item):
        return float(item.unit_cost())

    def get_allergen_list(self, item):
        return sorted(item.allergen_set())

    def get_recipe(self, item):
        if item.kind != Item.Kind.PREP:
            return []
        out = []
        for line in item.recipe_lines.select_related("component"):
            cost = line.component.unit_cost()
            out.append({
                "item": line.component_id, "name": line.component.name, "unit": line.component.unit,
                "qty": float(line.qty), "unit_cost": float(cost), "line_cost": float(line.qty * cost),
            })
        return out


class MenuItemSerializer(serializers.ModelSerializer):
    plate_cost = serializers.SerializerMethodField()
    food_cost_pct = serializers.SerializerMethodField()
    margin = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    allergens = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = ["id", "pos_code", "name", "category", "price", "is_active", "icon", "photo", "description", "diet",
                  "spice_level", "is_chef_pick", "is_new", "contains", "dietary_note", "pairs_with", "modifier_groups",
                  "sort_order", "plate_cost", "food_cost_pct", "margin", "lines", "allergens", "ingredient_allergens"]
        read_only_fields = ["photo"]

    ingredient_allergens = serializers.SerializerMethodField()

    def get_ingredient_allergens(self, m):
        return sorted(m.ingredient_allergens())

    def validate_spice_level(self, v):
        if v > 3:
            raise serializers.ValidationError("Spice goes from 0 (none) to 3.")
        return v

    def _cost(self, menu_item):
        # cache per object: several fields need it
        if not hasattr(menu_item, "_plate_cost"):
            menu_item._plate_cost = menu_item.plate_cost()
        return menu_item._plate_cost

    def get_plate_cost(self, m):
        return float(self._cost(m))

    def get_food_cost_pct(self, m):
        return float(self._cost(m) / m.price) if m.price else None

    def get_margin(self, m):
        return float(m.price - self._cost(m))

    def get_allergens(self, m):
        return sorted(m.allergen_set())

    def get_lines(self, m):
        out = []
        for line in m.lines.select_related("item"):
            cost = line.item.unit_cost()
            out.append({
                "item": line.item_id, "name": line.item.name, "unit": line.item.unit, "kind": line.item.kind,
                "qty": float(line.qty), "unit_cost": float(cost), "line_cost": float(line.qty * cost),
            })
        return out


class RecipeLineInSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=Item.objects.all())
    qty = serializers.DecimalField(max_digits=10, decimal_places=4, min_value=Decimal("0.0001"))


class RecipeInSerializer(serializers.Serializer):
    lines = RecipeLineInSerializer(many=True)
    price = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0"), required=False)

    def validate_lines(self, lines):
        ids = [line["item"].id for line in lines]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each ingredient can only appear once.")
        if not lines:
            raise serializers.ValidationError("A recipe needs at least one ingredient.")
        return lines


class PriceHistorySerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)

    class Meta:
        model = PriceHistory
        fields = ["id", "price", "recorded_on", "source", "vendor_name"]


class MenuCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "icon", "kind", "sort_order"]


class ModifierSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    item_name = serializers.CharField(source="item.name", read_only=True, default=None)

    class Meta:
        model = Modifier
        fields = ["id", "name", "price", "item", "item_name", "qty", "extra_item", "extra_qty", "allergens", "is_veg",
                  "is_default", "is_active", "sort_order"]


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierSerializer(many=True)
    dishes = serializers.SerializerMethodField()

    class Meta:
        model = ModifierGroup
        fields = ["id", "name", "label", "min_choices", "max_choices", "sort_order", "options", "dishes"]

    def get_dishes(self, g):
        return [{"id": d.id, "name": d.name} for d in g.menu_items.all()]

    def validate(self, data):
        lo, hi = data.get("min_choices", 0), data.get("max_choices", 1)
        if hi and lo > hi:
            raise serializers.ValidationError("Required picks can't be more than the maximum.")
        names = [o["name"].strip().lower() for o in data.get("options", [])]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Two options have the same name.")
        return data

    def _save_options(self, group, options):
        keep = []
        for i, o in enumerate(options):
            oid = o.pop("id", None)
            o.setdefault("sort_order", i)
            obj = (group.options.filter(pk=oid).first() if oid else None) or group.options.filter(name=o["name"]).first()
            if obj:
                for k, v in o.items():
                    setattr(obj, k, v)
                obj.save()
            else:
                obj = Modifier.objects.create(group=group, **o)
            keep.append(obj.id)
        # options already used on orders stay in history: retire rather than delete
        group.options.exclude(id__in=keep).update(is_active=False)

    def create(self, data):
        options = data.pop("options", [])
        group = ModifierGroup.objects.create(**data)
        self._save_options(group, options)
        return group

    def update(self, group, data):
        options = data.pop("options", None)
        for k, v in data.items():
            setattr(group, k, v)
        group.save()
        if options is not None:
            self._save_options(group, options)
        return group
