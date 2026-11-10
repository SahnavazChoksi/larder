"""Front of house: tables, orders (checks), kitchen tickets and payments."""
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models

from catalog.models import Location, MenuItem

User = settings.AUTH_USER_MODEL
CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


class Table(models.Model):
    class Shape(models.TextChoices):
        SQUARE = "square", "Square"
        ROUND = "round", "Round"
        LONG = "long", "Long"

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="tables")
    name = models.CharField(max_length=20)
    area = models.CharField(max_length=30, blank=True, help_text="e.g. Main, Patio, Bar")
    seats = models.PositiveSmallIntegerField(default=4)
    x = models.PositiveSmallIntegerField(default=0, help_text="Column on the floor plan grid (0–11)")
    y = models.PositiveSmallIntegerField(default=0, help_text="Row on the floor plan grid (0–7)")
    shape = models.CharField(max_length=6, choices=Shape.choices, default=Shape.SQUARE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["area", "name"]
        unique_together = [("location", "name")]

    def __str__(self):
        return f"{self.name} ({self.location.code})"


class Order(models.Model):
    """A check: everything one table (or one takeout/online/delivery order) orders and pays for."""

    class Type(models.TextChoices):
        DINE_IN = "dine_in", "Dine-in"
        TAKEOUT = "takeout", "Takeout"
        ONLINE = "online", "Online pickup"
        DELIVERY = "delivery", "Delivery app"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Paid"
        VOID = "void", "Void"

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="orders_pos")
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.DINE_IN)
    channel = models.CharField(max_length=20, default="larder", help_text="larder, website, uber_eats, doordash…")
    external_ref = models.CharField(max_length=80, blank=True, help_text="Order number on the delivery app")
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    guests = models.PositiveSmallIntegerField(default=1)
    server = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    guest = models.ForeignKey("guests.Guest", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    pickup_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    service_charge_rate = models.DecimalField(max_digits=5, decimal_places=4, default=ZERO)
    service_charge_removed = models.BooleanField(default=False)
    service_charge_removed_reason = models.CharField(max_length=120, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    discount_reason = models.CharField(max_length=120, blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)

    opened_at = models.DateTimeField()
    first_sent_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    business_date = models.DateField(db_index=True)
    void_reason = models.CharField(max_length=120, blank=True)
    public_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["location", "status"])]

    @property
    def number(self):
        return f"#{self.id}"

    def recalc(self, save=True):
        """Totals from live lines. Tax applies after discount and service charge."""
        subtotal = sum((line.qty * line.unit_price for line in self.lines.exclude(status=OrderLine.Status.VOID)), ZERO)
        discount = min(self.discount, subtotal)
        rate = ZERO if self.service_charge_removed else self.service_charge_rate
        sc = money((subtotal - discount) * rate)
        tax = money((subtotal - discount + sc) * self.location.tax_rate)
        self.subtotal, self.service_charge, self.tax = money(subtotal), sc, tax
        self.total = money(subtotal - discount + sc + tax)
        if save:
            self.save(update_fields=["subtotal", "service_charge", "tax", "total"])
        return self

    def paid(self) -> Decimal:
        return sum((p.amount - p.refunded_amount for p in self.payments.filter(status=Payment.Status.APPROVED)), ZERO)

    def tips(self) -> Decimal:
        return sum((p.tip for p in self.payments.filter(status=Payment.Status.APPROVED)), ZERO)

    def balance(self) -> Decimal:
        return money(self.total - self.paid())


class Ticket(models.Model):
    """One send to the kitchen. Its timestamps are where prep and service times come from."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        STARTED = "started", "Cooking"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        VOID = "void", "Void"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tickets")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="tickets")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.NEW)
    is_rush = models.BooleanField(default=False)
    sent_at = models.DateTimeField()
    sent_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sent_at"]
        indexes = [models.Index(fields=["location", "status"])]

    @staticmethod
    def minutes(a, b):
        return (b - a).total_seconds() / 60 if a and b else None

    @property
    def prep_minutes(self):
        return self.minutes(self.sent_at, self.ready_at)


class OrderLine(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Not sent"
        SENT = "sent", "Sent"
        VOID = "void", "Void"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.SET_NULL, related_name="lines")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    name = models.CharField(max_length=100, help_text="Copy of the dish name when ordered")
    qty = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    modifiers = models.JSONField(default=list, blank=True,
                                 help_text="Choices made when ordered: [{id, name, group, price}]; unit_price includes them")
    note = models.CharField(max_length=120, blank=True, help_text="e.g. extra spicy, no onion")
    seat = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=4, choices=Status.choices, default=Status.NEW)
    void_reason = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    @property
    def display_name(self):
        extras = ", ".join(m["name"] for m in self.modifiers)
        return f"{self.name} ({extras})" if extras else self.name


class Payment(models.Model):
    """One tender against an order. Card data never touches Larder: providers keep a reference only."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        GIFT = "gift", "Gift card"
        APP = "app", "Paid on delivery app"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for terminal"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=30, default="manual")
    method = models.CharField(max_length=6, choices=Method.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Towards the bill, excluding tip")
    tip = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    cash_tendered = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_ref = models.CharField(max_length=120, blank=True, help_text="Provider's payment id, e.g. a Stripe PaymentIntent")
    provider_data = models.JSONField(default=dict, blank=True, help_text="Non-sensitive details: card brand, last 4, auth code")
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def change_due(self):
        if self.method == self.Method.CASH and self.cash_tendered is not None:
            return money(self.cash_tendered - self.amount - self.tip)
        return None
