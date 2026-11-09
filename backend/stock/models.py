from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Item, Location

User = settings.AUTH_USER_MODEL


class Movement(models.Model):
    """The stock ledger. Stock on hand is the sum of movements; nobody types over a quantity.

    qty is signed (+ in, − out) in the item's unit. unit_cost is frozen at the time of the movement,
    so reports for past periods don't change when prices move later.
    """

    class Kind(models.TextChoices):
        OPENING = "opening", "Opening balance"
        PURCHASE = "purchase", "Delivery received"
        TRANSFER_IN = "transfer_in", "Transfer in"
        TRANSFER_OUT = "transfer_out", "Transfer out"
        SALE = "sale", "Sold (recipe usage)"
        WASTAGE = "wastage", "Wastage"
        COUNT = "count", "Count adjustment"
        PRODUCTION_IN = "production_in", "Produced"
        PRODUCTION_OUT = "production_out", "Used in production"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    qty = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4)
    occurred_on = models.DateField(db_index=True)
    reference = models.CharField(max_length=60, blank=True, help_text="e.g. PO-1042, TR-2201, COUNT-17")
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]
        indexes = [models.Index(fields=["location", "item", "occurred_on"])]

    @property
    def value(self) -> Decimal:
        return self.qty * self.unit_cost


class ParLevel(models.Model):
    """How much of an item a location should hold. Drives low-stock flags, reorders and prep requests."""

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="pars")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="pars")
    par = models.DecimalField(max_digits=12, decimal_places=3)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("location", "item")]


class StockCount(models.Model):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="counts")
    counted_on = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    value_difference = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-counted_on", "-id"]

    @property
    def number(self):
        return f"COUNT-{self.id}"


class StockCountLine(models.Model):
    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    system_qty = models.DecimalField(max_digits=14, decimal_places=4)
    counted_qty = models.DecimalField(max_digits=14, decimal_places=4)


class Wastage(models.Model):
    class Reason(models.TextChoices):
        SPOILED = "spoiled", "Spoiled"
        EXPIRED = "expired", "Expired"
        OVERPREP = "overprep", "Over-prepped"
        DROPPED = "dropped", "Dropped / spilled"
        QUALITY = "quality", "Quality reject"
        STAFF = "staff", "Staff meal"
        RETURN = "return", "Customer return"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="wastage")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4)
    reason = models.CharField(max_length=10, choices=Reason.choices)
    note = models.CharField(max_length=200, blank=True)
    occurred_on = models.DateField()
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]


class Transfer(models.Model):
    """Stock moving between locations, usually prep from the central kitchen to an outlet."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        DISPATCHED = "dispatched", "Dispatched"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    from_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="transfers_out")
    to_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="transfers_in")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    note = models.CharField(max_length=200, blank=True)
    requested_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    requested_on = models.DateField()
    dispatched_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    dispatched_on = models.DateField(null=True, blank=True)
    received_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-requested_on", "-id"]

    @property
    def number(self):
        return f"TR-{self.id}"


class TransferLine(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    qty_requested = models.DecimalField(max_digits=12, decimal_places=4)
    qty_sent = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    qty_received = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)


class ProductionBatch(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        DONE = "done", "Cooked"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="batches")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, limit_choices_to={"kind": "prep"})
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PLANNED)
    planned_for = models.DateField()
    completed_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    completed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-planned_for", "-id"]
        verbose_name_plural = "production batches"

    @property
    def number(self):
        return f"B-{self.id}"
