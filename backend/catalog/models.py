from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

ZERO = Decimal("0")


class Location(models.Model):
    class Kind(models.TextChoices):
        OUTLET = "outlet", "Outlet"
        KITCHEN = "kitchen", "Central kitchen"

    code = models.CharField(max_length=12, unique=True, help_text="Short code used in POS exports, e.g. SQ1")
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=60, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OUTLET)
    brand = models.CharField(max_length=60, blank=True, help_text="Outlets are compared with others of the same brand")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.13"), help_text="Sales tax, e.g. 0.13 for Ontario HST")
    service_charge_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.15"),
                                              help_text="Automatic service charge for large parties")
    service_charge_party = models.PositiveSmallIntegerField(default=6, help_text="Party size that gets the service charge")
    accepts_online_orders = models.BooleanField(default=False)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name


class Vendor(models.Model):
    name = models.CharField(max_length=100, unique=True)
    lead_days = models.PositiveSmallIntegerField(default=1, help_text="Days from order to delivery")
    delivery_days = models.CharField(max_length=60, blank=True, help_text="e.g. Mon, Wed, Fri")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    """Anything held in stock: a bought ingredient (raw) or something made in-house (prep)."""

    class Kind(models.TextChoices):
        RAW = "raw", "Raw ingredient"
        PREP = "prep", "Prep (made in-house)"

    class Unit(models.TextChoices):
        KG = "kg", "kg"
        L = "L", "L"
        PC = "pc", "pc"

    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=40)
    unit = models.CharField(max_length=4, choices=Unit.choices)
    kind = models.CharField(max_length=4, choices=Kind.choices, default=Kind.RAW)
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    last_price = models.DecimalField(
        max_digits=10, decimal_places=4, default=ZERO, validators=[MinValueValidator(ZERO)],
        help_text="Latest purchase price per unit (raw items). Updated when deliveries are received.",
    )
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True)
    batch_size = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, help_text="Usual batch (preps)")
    allergens = models.CharField(max_length=120, blank=True, help_text="Comma separated, e.g. Dairy, Gluten")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def unit_cost(self, _depth: int = 0) -> Decimal:
        """Cost of one unit. Raw items use the latest price; preps add up their recipe."""
        if self.kind == self.Kind.RAW:
            return self.last_price
        if _depth > 6:  # guards against a recipe that (wrongly) contains itself
            return ZERO
        total = ZERO
        for line in self.recipe_lines.select_related("component"):
            total += line.qty * line.component.unit_cost(_depth + 1)
        return total

    def allergen_set(self, _depth: int = 0) -> set[str]:
        found = {a.strip() for a in self.allergens.split(",") if a.strip()}
        if self.kind == self.Kind.PREP and _depth <= 6:
            for line in self.recipe_lines.select_related("component"):
                found |= line.component.allergen_set(_depth + 1)
        return found


class RecipeLine(models.Model):
    """One ingredient of a prep recipe, per 1 unit of the prep's output (yield losses included)."""

    prep = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="recipe_lines")
    component = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="used_in_preps")
    qty = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(ZERO)])

    class Meta:
        unique_together = [("prep", "component")]


class MenuItem(models.Model):
    pos_code = models.CharField(max_length=20, unique=True, help_text="Code the POS uses for this dish")
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=40)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(ZERO)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name

    def plate_cost(self) -> Decimal:
        total = ZERO
        for line in self.lines.select_related("item"):
            total += line.qty * line.item.unit_cost()
        return total

    def allergen_set(self) -> set[str]:
        found: set[str] = set()
        for line in self.lines.select_related("item"):
            found |= line.item.allergen_set()
        return found


class MenuLine(models.Model):
    """What one portion of a dish uses, in the stock unit of each item."""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="menu_lines")
    qty = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(ZERO)])

    class Meta:
        unique_together = [("menu_item", "item")]


class PriceHistory(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="price_history")
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL)
    price = models.DecimalField(max_digits=10, decimal_places=4)
    recorded_on = models.DateField()
    source = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-recorded_on", "-id"]
