"""Guests: profiles, loyalty points, reservations and the walk-in waitlist."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Location

User = settings.AUTH_USER_MODEL


class Guest(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    birthday = models.DateField(null=True, blank=True)
    allergies = models.CharField(max_length=200, blank=True)
    notes = models.CharField(max_length=300, blank=True, help_text="Preferences: favourite table, spice level…")
    is_member = models.BooleanField(default=False, help_text="Enrolled in the loyalty program")
    joined_on = models.DateField(null=True, blank=True)
    marketing_opt_in = models.BooleanField(default=False, help_text="Agreed to receive offers (CASL consent)")
    points = models.IntegerField(default=0)
    visits = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    last_visit = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PointsEntry(models.Model):
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="points_history")
    order = models.ForeignKey("pos.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    points = models.IntegerField()
    reason = models.CharField(max_length=80)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Reservation(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        ARRIVED = "arrived", "Arrived"
        SEATED = "seated", "Seated"
        NO_SHOW = "no_show", "No-show"
        CANCELLED = "cancelled", "Cancelled"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="reservations")
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    party_size = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=90)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    table = models.ForeignKey("pos.Table", null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    notes = models.CharField(max_length=200, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    seated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]


class WaitlistEntry(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        NOTIFIED = "notified", "Told table is ready"
        SEATED = "seated", "Seated"
        LEFT = "left", "Left"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="waitlist")
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True)
    party_size = models.PositiveSmallIntegerField()
    quoted_minutes = models.PositiveSmallIntegerField(default=15)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    table = models.ForeignKey("pos.Table", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.CharField(max_length=200, blank=True)
    added_at = models.DateTimeField()
    notified_at = models.DateTimeField(null=True, blank=True)
    seated_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["added_at"]
        verbose_name_plural = "waitlist entries"

    @property
    def waited_minutes(self):
        end = self.seated_at or self.left_at
        return (end - self.added_at).total_seconds() / 60 if end else None


class Message(models.Model):
    """Every text/email sent to a guest, whatever the provider. Lets you audit what guests were told."""

    location = models.ForeignKey(Location, null=True, on_delete=models.SET_NULL, related_name="+")
    to = models.CharField(max_length=120)
    body = models.CharField(max_length=480)
    provider = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default="sent")
    provider_ref = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
