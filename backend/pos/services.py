"""Order lifecycle: open → add items → send to kitchen → pay → close (books sales, stock and loyalty)."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import Modifier
from sales.models import SalesDay, SalesLine
from stock.models import Movement
from stock.services import fail, record

from . import payments as providers
from .models import ZERO, Order, OrderLine, Payment, Ticket, money


# ---------- opening and editing ----------

def _auto_service_charge(order: Order):
    loc = order.location
    if order.type == Order.Type.DINE_IN and order.guests >= loc.service_charge_party and not order.service_charge_removed:
        order.service_charge_rate = loc.service_charge_rate
    elif order.type != Order.Type.DINE_IN or order.guests < loc.service_charge_party:
        order.service_charge_rate = ZERO


def _require_open(order: Order):
    if order.status != Order.Status.OPEN:
        fail(f"Order {order.number} is {order.get_status_display().lower()}.")


@transaction.atomic
def open_order(location, user, *, type=Order.Type.DINE_IN, table=None, guests=1, guest=None, customer_name="",
               customer_phone="", channel="larder", external_ref="", note="", pickup_at=None, at=None,
               check_table=True) -> Order:
    if table is not None:
        if table.location_id != location.id:
            fail("That table belongs to another location.")
        busy = Order.objects.filter(table=table, status=Order.Status.OPEN).first() if check_table else None
        if busy:
            fail(f"{table.name} already has an open check ({busy.number}).")
    if type == Order.Type.DINE_IN and table is None:
        fail("Pick a table for a dine-in order.")
    at = at or timezone.now()
    order = Order(location=location, table=table, type=type, guests=max(1, guests), server=user, guest=guest,
                  customer_name=customer_name or (guest.name if guest else ""), customer_phone=customer_phone,
                  channel=channel, external_ref=external_ref, note=note, pickup_at=pickup_at, opened_at=at,
                  business_date=timezone.localdate(at))
    _auto_service_charge(order)
    order.save()
    return order


def resolve_modifiers(menu_item, ids, *, defaults=False) -> list[Modifier]:
    """Check the chosen options against the dish's groups. defaults=True fills required picks nobody made
    (used for delivery-app and seed orders, where the app has already asked the guest)."""
    ids = list(ids or [])
    if len(ids) != len(set(ids)):
        fail("Each option can only be picked once.")
    groups = {g.id: g for g in menu_item.modifier_groups.all()}
    chosen = list(Modifier.objects.filter(id__in=ids, is_active=True).select_related("group"))
    if len(chosen) != len(ids):
        fail("One of the options isn't available any more.")
    by_group: dict[int, list[Modifier]] = {}
    for m in chosen:
        if m.group_id not in groups:
            fail(f"{m.name} isn't an option for {menu_item.name}.")
        by_group.setdefault(m.group_id, []).append(m)
    for g in groups.values():
        picked = by_group.get(g.id, [])
        if defaults and len(picked) < g.min_choices:
            extra = [m for m in g.options.filter(is_active=True).order_by("-is_default", "sort_order", "id")
                     if m not in picked][:g.min_choices - len(picked)]
            picked = picked + extra
            chosen += extra
        if len(picked) < g.min_choices:
            fail(f"Pick {'a' if g.min_choices == 1 else g.min_choices} {g.name.lower()} for {menu_item.name}.")
        if g.max_choices and len(picked) > g.max_choices:
            fail(f"{menu_item.name}: up to {g.max_choices} {g.name.lower()}.")
    return sorted(chosen, key=lambda m: (m.group.sort_order, m.group_id, m.sort_order, m.id))


def add_line(order: Order, menu_item, qty: int, user, note="", seat=None, price=None, modifiers=None,
             default_modifiers=False, allow_inactive=False) -> OrderLine:
    _require_open(order)
    if not menu_item.is_active and not allow_inactive:
        fail(f"{menu_item.name} is off the menu.")
    if not 1 <= qty <= 99:
        fail("Quantity must be between 1 and 99.")
    mods = resolve_modifiers(menu_item, modifiers, defaults=default_modifiers)
    base = menu_item.price if price is None else price
    line = OrderLine.objects.create(order=order, menu_item=menu_item, name=menu_item.name, qty=qty,
                                    unit_price=money(base + sum((m.price for m in mods), ZERO)), note=note[:120], seat=seat,
                                    modifiers=[{"id": m.id, "name": m.name, "group": m.group.name, "price": float(m.price)}
                                               for m in mods],
                                    created_by=user)
    order.recalc()
    return line


def change_line(line: OrderLine, qty=None, note=None):
    _require_open(line.order)
    if line.status != OrderLine.Status.NEW:
        fail("This item is already with the kitchen. Void it instead.")
    if qty is not None:
        if qty == 0:
            line.delete()
            line.order.recalc()
            return None
        if not 1 <= qty <= 99:
            fail("Quantity must be between 1 and 99.")
        line.qty = qty
    if note is not None:
        line.note = note[:120]
    line.save()
    line.order.recalc()
    return line


def void_line(line: OrderLine, reason: str, user):
    _require_open(line.order)
    if line.status == OrderLine.Status.VOID:
        return line
    if line.status == OrderLine.Status.SENT and not reason.strip():
        fail("Say why the item is being voided (e.g. guest changed mind, kitchen error).")
    line.status, line.void_reason = OrderLine.Status.VOID, reason.strip()
    line.save(update_fields=["status", "void_reason"])
    line.order.recalc()
    return line


def set_guests(order: Order, guests: int):
    _require_open(order)
    order.guests = max(1, guests)
    _auto_service_charge(order)
    order.save(update_fields=["guests", "service_charge_rate"])
    order.recalc()


def remove_service_charge(order: Order, reason: str):
    _require_open(order)
    if not order.service_charge_rate:
        fail("This order has no service charge.")
    if not reason.strip():
        fail("Say why the guest asked for it to be removed.")
    order.service_charge_removed, order.service_charge_removed_reason = True, reason.strip()
    order.save(update_fields=["service_charge_removed", "service_charge_removed_reason"])
    order.recalc()


def apply_discount(order: Order, amount: Decimal, reason: str):
    _require_open(order)
    if amount < 0:
        fail("A discount can't be negative.")
    if amount and not reason.strip():
        fail("Say why the discount is given (e.g. comp for slow service, staff meal).")
    order.discount, order.discount_reason = money(amount), reason.strip()
    order.save(update_fields=["discount", "discount_reason"])
    order.recalc()


@transaction.atomic
def redeem_points(order: Order, rewards: int, user):
    from guests.models import Guest, PointsEntry

    _require_open(order)
    if not order.guest_id:
        fail("Attach the guest's profile first.")
    guest = Guest.objects.select_for_update().get(pk=order.guest_id)
    cost = rewards * settings.LOYALTY_REWARD_POINTS
    if rewards < 1 or guest.points < cost:
        fail(f"{guest.name} has {guest.points} points; each reward needs {settings.LOYALTY_REWARD_POINTS}.")
    guest.points -= cost
    guest.save(update_fields=["points"])
    PointsEntry.objects.create(guest=guest, order=order, points=-cost, reason=f"Redeemed on order {order.number}", created_by=user)
    order.discount = money(order.discount + settings.LOYALTY_REWARD_VALUE * rewards)
    order.discount_reason = (order.discount_reason + "; " if order.discount_reason else "") + f"Loyalty reward ×{rewards}"
    order.save(update_fields=["discount", "discount_reason"])
    order.recalc()


# ---------- kitchen ----------

@transaction.atomic
def send_to_kitchen(order: Order, user, rush=False, at=None) -> Ticket:
    _require_open(order)
    lines = list(order.lines.filter(status=OrderLine.Status.NEW))
    if not lines:
        fail("Nothing new to send.")
    at = at or timezone.now()
    ticket = Ticket.objects.create(order=order, location=order.location, sent_at=at, sent_by=user, is_rush=rush)
    OrderLine.objects.filter(id__in=[line.id for line in lines]).update(status=OrderLine.Status.SENT, ticket=ticket)
    if not order.first_sent_at:
        order.first_sent_at = at
        order.save(update_fields=["first_sent_at"])
    return ticket


def _day(location, business_date) -> SalesDay:
    day, _ = SalesDay.objects.get_or_create(location=location, business_date=business_date, defaults={"source": "Larder POS"})
    return day


def ticket_step(ticket: Ticket, step: str, at=None) -> Ticket:
    """start | ready | served | recall. 'ready' adds the ticket's prep time to the day's KDS totals."""
    at = at or timezone.now()
    allowed = {"start": (Ticket.Status.NEW,), "ready": (Ticket.Status.NEW, Ticket.Status.STARTED),
               "served": (Ticket.Status.READY,), "recall": (Ticket.Status.READY, Ticket.Status.SERVED)}
    if step not in allowed:
        fail("Unknown step.")
    if ticket.status not in allowed[step]:
        fail(f"Ticket is {ticket.get_status_display().lower()}.")
    if step == "start":
        ticket.status, ticket.started_at = Ticket.Status.STARTED, at
    elif step == "ready":
        ticket.status, ticket.ready_at = Ticket.Status.READY, at
        ticket.started_at = ticket.started_at or ticket.sent_at
        minutes = Decimal(str(round(ticket.prep_minutes, 1)))
        day = _day(ticket.location, ticket.order.business_date)
        SalesDay.objects.filter(pk=day.pk).update(tickets=F("tickets") + 1, prep_minutes=F("prep_minutes") + minutes)
    elif step == "served":
        ticket.status, ticket.served_at = Ticket.Status.SERVED, at
    else:  # recall: back on the board, e.g. dish sent back
        ticket.status, ticket.served_at = Ticket.Status.STARTED, None
    ticket.save()
    return ticket


# ---------- payments ----------

@transaction.atomic
def take_payment(order: Order, user, *, provider="manual", method=Payment.Method.CARD, amount=None, tip=ZERO,
                 cash_tendered=None, reference="") -> tuple[Payment, providers.StartResult]:
    _require_open(order)
    order.recalc()
    balance = order.balance()
    amount = balance if amount is None else money(amount)
    if amount <= 0:
        fail("Nothing left to pay." if balance <= 0 else "Enter an amount above zero.")
    if amount > balance:
        fail(f"That's more than the ${balance} left. Put the extra as a tip or give change.")
    if tip < 0:
        fail("A tip can't be negative.")
    try:
        p = providers.get(provider)
    except providers.PaymentError as exc:
        fail(str(exc))
    if method not in p.methods:
        fail(f"{p.label} doesn't take {Payment.Method(method).label.lower()} payments.")
    payment = Payment.objects.create(order=order, provider=p.key, method=method, amount=amount, tip=money(tip),
                                     cash_tendered=cash_tendered, created_by=user,
                                     provider_data={"reference": reference[:60]} if reference else {})
    try:
        result = p.start(payment)
    except providers.PaymentError as exc:
        payment.status = Payment.Status.DECLINED
        payment.save(update_fields=["status"])
        fail(str(exc))
    if result.status == Payment.Status.APPROVED:
        providers.approve(payment)
    else:
        payment.status = result.status
        payment.save(update_fields=["status"])
    return payment, result


@transaction.atomic
def refund(payment: Payment, amount: Decimal, user):
    if payment.status != Payment.Status.APPROVED:
        fail("Only approved payments can be refunded.")
    amount = money(amount)
    if amount <= 0 or amount > payment.amount - payment.refunded_amount:
        fail(f"Refund between $0.01 and ${payment.amount - payment.refunded_amount}.")
    try:
        providers.get(payment.provider).refund(payment, amount)
    except providers.PaymentError as exc:
        fail(str(exc))
    payment.refunded_amount = money(payment.refunded_amount + amount)
    payment.save(update_fields=["refunded_amount"])
    return payment


# ---------- closing ----------

@transaction.atomic
def close_order(order: Order, user, at=None) -> Order:
    """Paid in full → closed. Books the sale (sales lines, covers, service charge, loyalty) and stock usage."""
    _require_open(order)
    if order.lines.filter(status=OrderLine.Status.NEW).exists():
        fail("Some items haven't been sent to the kitchen. Send or remove them first.")
    if not order.lines.exclude(status=OrderLine.Status.VOID).exists():
        fail("The order is empty. Void it instead.")
    order.recalc()
    if order.balance() > Decimal("0.00"):
        fail(f"${order.balance()} still to pay.")
    order.status, order.closed_at, order.closed_by = Order.Status.CLOSED, at or timezone.now(), user
    order.save(update_fields=["status", "closed_at", "closed_by"])
    book_sale(order, user)
    if order.guest_id:
        earn_points(order, user)
    return order


def book_sale(order: Order, user):
    lines = list(order.lines.exclude(status=OrderLine.Status.VOID).select_related("menu_item"))
    share = (order.subtotal - order.discount) / order.subtotal if order.subtotal else Decimal(1)
    day = _day(order.location, order.business_date)
    SalesLine.objects.bulk_create(
        SalesLine(day=day, order=order, menu_item=line.menu_item, qty=line.qty, net_sales=money(line.qty * line.unit_price * share))
        for line in lines
    )
    member = bool(order.guest_id and order.guest.is_member)
    SalesDay.objects.filter(pk=day.pk).update(
        covers=F("covers") + (order.guests if order.type == Order.Type.DINE_IN else 0),
        bills=F("bills") + 1,
        sc_bills=F("sc_bills") + (1 if order.service_charge_rate else 0),
        sc_removed=F("sc_removed") + (1 if order.service_charge_rate and order.service_charge_removed else 0),
        loyalty_bills=F("loyalty_bills") + (1 if member else 0),
    )
    usage: dict[int, list] = {}
    mod_ids = {m["id"] for line in lines for m in line.modifiers}
    mods = {m.id: m for m in Modifier.objects.filter(id__in=mod_ids).select_related("item", "extra_item")}

    def use(item, qty):
        entry = usage.setdefault(item.id, [item, Decimal(0)])
        entry[1] += qty

    for line in lines:
        for ml in line.menu_item.lines.select_related("item"):
            use(ml.item, ml.qty * line.qty)
        for chosen in line.modifiers:
            m = mods.get(chosen["id"])
            for item, qty in (m.usage() if m else []):
                use(item, qty * line.qty)
    for item, qty in usage.values():
        record(order.location, item, Movement.Kind.SALE, -qty, user, f"ORDER-{order.id}", order.business_date)


def earn_points(order: Order, user):
    from guests.models import Guest, PointsEntry

    guest = Guest.objects.select_for_update().get(pk=order.guest_id)
    spend = order.subtotal - order.discount
    guest.visits += 1
    guest.total_spent += spend
    guest.last_visit = order.business_date
    fields = ["visits", "total_spent", "last_visit"]
    if guest.is_member:
        points = int(spend * settings.LOYALTY_POINTS_PER_DOLLAR)
        if points > 0:
            guest.points += points
            fields.append("points")
            PointsEntry.objects.create(guest=guest, order=order, points=points, reason=f"Order {order.number}", created_by=user)
    guest.save(update_fields=fields)


@transaction.atomic
def void_order(order: Order, reason: str, user):
    _require_open(order)
    if order.payments.filter(status=Payment.Status.APPROVED).exists():
        fail("This order has payments. Refund them first.")
    if not reason.strip():
        fail("Say why the order is being voided.")
    order.lines.exclude(status=OrderLine.Status.VOID).update(status=OrderLine.Status.VOID, void_reason=reason.strip())
    order.tickets.exclude(status=Ticket.Status.SERVED).update(status=Ticket.Status.VOID)
    order.status, order.void_reason, order.closed_at, order.closed_by = Order.Status.VOID, reason.strip(), timezone.now(), user
    order.save(update_fields=["status", "void_reason", "closed_at", "closed_by"])
    order.recalc()


# ---------- orders taken while the server was unreachable ----------

ROUNDING = Decimal("0.50")  # what we let a tablet's own total differ from ours before asking a manager
CENTS = Decimal("0.05")


@transaction.atomic
def import_offline_order(location, user, d: dict, device: str = "") -> tuple[Order, str]:
    """Book an order a tablet took offline, with its real times. Returns (order, outcome).

    outcome: "duplicate" (already uploaded), "closed" (paid in full and booked) or "open" (still running, or the
    payments don't cover our total, so a manager should look). Raises ValidationError if it can't be booked;
    nothing is saved then and the tablet keeps it.
    """
    from catalog.models import MenuItem

    from .models import Table

    existing = Order.objects.filter(client_id=d["client_id"]).first()
    if existing:
        return existing, "duplicate"
    table = None
    if d.get("table"):
        table = Table.objects.filter(pk=d["table"], location=location).first()
        if not table:
            fail("That table no longer exists.")
    closed_at = d.get("closed_at")
    order = open_order(location, user, type=d["type"], table=table, guests=d.get("guests", 1),
                       customer_name=d.get("customer_name", ""), note=f"Taken offline{f' on {device}' if device else ''}",
                       at=d["opened_at"], check_table=not closed_at)
    order.client_id = d["client_id"]
    order.save(update_fields=["client_id"])

    dishes = {m.id: m for m in MenuItem.objects.filter(id__in=[x["menu_item"] for x in d["lines"]])}
    sends: dict = {}
    for x in d["lines"]:
        dish = dishes.get(x["menu_item"])
        if not dish:
            fail("A dish on this order has been deleted.")
        line = add_line(order, dish, x["qty"], user, note=x.get("note", ""), price=x["price"], modifiers=x.get("modifiers"),
                        allow_inactive=True)
        sent = x.get("sent_at") or closed_at
        if sent:
            sends.setdefault(sent, []).append(line.id)
    # The kitchen cooked from paper tickets, so these tickets are history: served, and kept out of prep-time stats.
    for at in sorted(sends):
        ticket = Ticket.objects.create(order=order, location=location, sent_at=at, sent_by=user,
                                       status=Ticket.Status.SERVED, served_at=closed_at or at)
        OrderLine.objects.filter(id__in=sends[at]).update(status=OrderLine.Status.SENT, ticket=ticket)
    if sends:
        order.first_sent_at = min(sends)
        order.save(update_fields=["first_sent_at"])

    order.refresh_from_db()
    order.recalc()
    payments = d.get("payments", [])
    for n, p in enumerate(payments):
        balance = order.balance()
        amount, tip = money(p["amount"]), money(p.get("tip", 0))
        short = balance - amount
        if closed_at and n == len(payments) - 1 and ZERO < short <= CENTS:
            # the tablet rounded a cent differently: it's the same money, so count it toward the bill, not the tip
            amount, tip = balance, max(ZERO, tip - short)
        if amount > balance:
            if amount - balance > ROUNDING:
                fail(f"Payments add up to more than the bill (${amount} against ${balance} left).")
            amount = balance
        if amount <= 0:
            continue
        take_payment(order, user, provider="manual", method=p["method"], amount=amount, tip=tip,
                     cash_tendered=p.get("cash_tendered"), reference=p.get("reference", ""))
    order.refresh_from_db()
    if closed_at and order.balance() <= 0:
        close_order(order, user, at=closed_at)
        return order, "closed"
    return order, "open"
