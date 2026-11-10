from django.conf import settings
from django.db import models

from catalog.models import Location, MenuItem


class SalesDay(models.Model):
    """One business day of sales at one location, as exported from the POS. Re-importing replaces it."""

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="sales_days")
    business_date = models.DateField()
    source = models.CharField(max_length=40, default="CSV import")
    covers = models.PositiveIntegerField(default=0, help_text="Guests served")
    bills = models.PositiveIntegerField(default=0, help_text="Bills / checks closed")
    sc_bills = models.PositiveIntegerField(default=0, help_text="Bills that had a service charge")
    sc_removed = models.PositiveIntegerField(default=0, help_text="Bills where the service charge was taken off")
    is_history = models.BooleanField(default=False, help_text="Imported past sales: used for trends, no stock usage booked")
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("location", "business_date")]
        ordering = ["-business_date", "location__name"]

    @property
    def reference(self):
        return f"SALES-{self.id}"


class SalesLine(models.Model):
    day = models.ForeignKey(SalesDay, on_delete=models.CASCADE, related_name="lines")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField()
    net_sales = models.DecimalField(max_digits=12, decimal_places=2)
