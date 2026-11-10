"""Day-to-day operations: people, guest complaints, equipment issues, handover notes, notifications."""
from django.conf import settings
from django.db import models

from catalog.models import Location

User = settings.AUTH_USER_MODEL


class Department(models.TextChoices):
    SERVICE = "service", "Service"
    KITCHEN = "kitchen", "Kitchen"
    DELIVERY = "delivery", "Delivery / packing"
    MANAGEMENT = "management", "Management"


class StaffingPlan(models.Model):
    """How many people a location should have in a department (the 'required' row)."""

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="staffing_plan")
    department = models.CharField(max_length=12, choices=Department.choices)
    required = models.PositiveSmallIntegerField()
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("location", "department")]


class Employee(models.Model):
    """Someone on the payroll. Not every employee needs a Larder login."""

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="employees")
    department = models.CharField(max_length=12, choices=Department.choices)
    name = models.CharField(max_length=100)
    position = models.CharField(max_length=60, blank=True, help_text="e.g. Server, Tandoor chef")
    started_on = models.DateField(null=True, blank=True)
    left_on = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee")

    class Meta:
        ordering = ["location", "department", "name"]

    def __str__(self):
        return self.name


class Complaint(models.Model):
    class Category(models.TextChoices):
        FOOD = "food", "Food quality"
        SERVICE = "service", "Service"
        WAIT = "wait", "Wait time"
        ACCURACY = "accuracy", "Wrong or missing item"
        CLEAN = "clean", "Cleanliness"
        PRICE = "price", "Price / bill"

    class Channel(models.TextChoices):
        IN_PERSON = "in_person", "In person"
        PHONE = "phone", "Phone"
        REVIEW = "review", "Online review"
        DELIVERY = "delivery", "Delivery app"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="complaints")
    occurred_on = models.DateField()
    category = models.CharField(max_length=10, choices=Category.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.IN_PERSON)
    detail = models.CharField(max_length=300)
    action_taken = models.CharField(max_length=300, blank=True)
    comped = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Value given back to the guest")
    logged_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_on", "-id"]


class Equipment(models.Model):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="equipment")
    name = models.CharField(max_length=80, help_text="e.g. Walk-in cooler, Fryer 2")
    category = models.CharField(max_length=40, blank=True, help_text="Refrigeration, Cooking, Dish, HVAC…")
    serial = models.CharField(max_length=60, blank=True)
    service_contact = models.CharField(max_length=120, blank=True, help_text="Who fixes it, with phone number")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["location", "name"]
        verbose_name_plural = "equipment"

    def __str__(self):
        return f"{self.name} ({self.location})"


class Issue(models.Model):
    """Something broken or unsafe, tracked until it's fixed. Can be raised from a failed checklist task."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "Being fixed"
        RESOLVED = "resolved", "Fixed"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="issues")
    equipment = models.ForeignKey(Equipment, null=True, blank=True, on_delete=models.SET_NULL, related_name="issues")
    title = models.CharField(max_length=140)
    detail = models.TextField(blank=True)
    severity = models.CharField(max_length=8, choices=Severity.choices, default=Severity.HIGH)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    assigned_to = models.CharField(max_length=120, blank=True, help_text="Technician, vendor or staff member")
    source_answer = models.ForeignKey("checklists.RunAnswer", null=True, blank=True, on_delete=models.SET_NULL, related_name="issues")
    raised_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=300, blank=True)
    repair_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]

    @property
    def number(self):
        return f"ISS-{self.id}"


class HandoverNote(models.Model):
    """The logbook: what the next shift needs to know."""

    class Shift(models.TextChoices):
        OPENING = "opening", "Opening / day"
        CLOSING = "closing", "Closing / night"
        GENERAL = "general", "General"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="handover_notes")
    business_date = models.DateField()
    shift = models.CharField(max_length=8, choices=Shift.choices, default=Shift.GENERAL)
    body = models.TextField()
    is_important = models.BooleanField(default=False)
    author = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(User, blank=True, related_name="+")

    class Meta:
        ordering = ["-business_date", "-created_at"]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=400, blank=True)
    link = models.CharField(max_length=200, blank=True)
    severity = models.CharField(max_length=8, default="info")
    key = models.CharField(max_length=120, blank=True, help_text="Stops the same alert being sent twice")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]
        constraints = [models.UniqueConstraint(fields=["user", "key"], condition=~models.Q(key=""), name="one_alert_per_key")]
