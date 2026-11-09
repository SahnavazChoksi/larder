from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Item, Location, Vendor

User = settings.AUTH_USER_MODEL


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        REORDER = "reorder", "Reorder suggestion"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="orders")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    note = models.CharField(max_length=200, blank=True)
    invoice_number = models.CharField(max_length=40, blank=True)
    expected_on = models.DateField(null=True, blank=True)
    created_on = models.DateField()
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    sent_on = models.DateField(null=True, blank=True)
    received_on = models.DateField(null=True, blank=True)
    received_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_on", "-id"]

    @property
    def number(self):
        return f"PO-{1000 + self.id}"

    def total(self) -> Decimal:
        total = Decimal("0")
        for line in self.lines.all():
            if self.status == self.Status.RECEIVED and line.qty_received is not None:
                total += line.qty_received * (line.price_received or line.unit_price)
            else:
                total += line.qty * line.unit_price
        return total


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=4)
    unit_price = models.DecimalField(max_digits=10, decimal_places=4)
    qty_received = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    price_received = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
