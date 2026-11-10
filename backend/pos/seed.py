"""Demo front of house: tables, guests, a few days of POS service with real timings, and a live service.

Called by `manage.py seed_demo`. Square One "went live" on Larder's POS for the last few days; the other
outlets keep importing CSVs, which is how most rollouts look.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from catalog.models import MenuCategory
from guests.models import Guest, Reservation, WaitlistEntry

from . import services
from .models import Order, Payment, Table

FIRST = ["Ava", "Ben", "Chloe", "Dev", "Ella", "Farhan", "Gia", "Harpreet", "Ivan", "Jade", "Kabir", "Lena", "Marco",
         "Nina", "Owen", "Pooja", "Quinn", "Rohan", "Sana", "Tom", "Uma", "Vik", "Wen", "Yara", "Zain"]
LAST = ["Ahmed", "Bains", "Costa", "Dhillon", "Evans", "Fong", "Grewal", "Hughes", "Iyer", "Jones", "Kapoor", "Lam"]
# name, area, seats, x, y, shape
TABLES = [("T1", "Window", 2, 0, 0, "square"), ("T2", "Window", 2, 2, 0, "square"), ("T3", "Window", 4, 4, 0, "square"),
          ("T4", "Window", 4, 6, 0, "square"), ("T5", "Main", 4, 0, 2, "round"), ("T6", "Main", 4, 2, 2, "round"),
          ("T7", "Main", 4, 4, 2, "round"), ("T8", "Main", 6, 6, 2, "long"), ("T9", "Main", 8, 9, 2, "long"),
          ("T10", "Booths", 4, 0, 5, "square"), ("T11", "Booths", 4, 2, 5, "square"), ("T12", "Booths", 4, 4, 5, "square"),
          ("P1", "Patio", 4, 9, 5, "round"), ("P2", "Patio", 2, 11, 5, "round")]
LUNCH, DINNER = (time(11, 30), 180), (time(17, 0), 270)  # start, minutes long


def seed_tables(outlets):
    for loc in outlets:
        rows = TABLES if loc.code == "SQ1" else TABLES[:11]
        Table.objects.bulk_create(Table(location=loc, name=n, area=a, seats=s, x=x, y=y, shape=sh) for n, a, s, x, y, sh in rows)


def seed_guests(rng, today, count=140):
    guests = []
    for i in range(count):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        member = rng.random() < 0.45
        guests.append(Guest(name=name, phone=f"416555{1000 + i:04d}", email=f"guest{i}@example.com",
                            is_member=member, joined_on=today - timedelta(days=rng.randint(10, 400)) if member else None,
                            marketing_opt_in=member and rng.random() < 0.6,
                            allergies=rng.choice(["", "", "", "", "", "", "Peanuts", "Egg", "Dairy", "Mushrooms",
                                                       "Tree nuts", "Gluten"]),
                            points=rng.randint(0, 260) if member else 0))
    Guest.objects.bulk_create(guests)
    return list(Guest.objects.all())


def _at(day, start, length, rng):
    t = datetime.combine(day, start) + timedelta(minutes=rng.randint(0, length))
    return timezone.make_aware(t)


NOTES = ["", "", "", "", "no pickles", "sauce on the side", "no onion", "extra crispy", "cut in half"]


def _options(dish, rng, stocked):
    """What a guest might pick: mostly the usual, sometimes a bigger size or an add-on the outlet has in stock."""
    picks = []
    for g in dish.modifier_groups.all():
        options = [m for m in g.options.all() if m.is_active and all(i.id in stocked for i, _ in m.usage())]
        if not options:
            continue
        if g.min_choices:
            usual = next((m for m in options if m.is_default), options[0])
            picks.append(rng.choice(options) if rng.random() < 0.3 else usual)
        elif rng.random() < 0.18:
            picks.append(rng.choice(options))
    return [m.id for m in picks]


def _add(order, dish, qty, server, rng, stocked, note=None):
    services.add_line(order, dish, qty, server, note=rng.choice(NOTES) if note is None else note,
                      modifiers=_options(dish, rng, stocked), default_modifiers=True)


def run_service_day(outlet, day, plan, server, guests, rng, busy=1.0, stocked=frozenset()) -> dict:
    """Turn a day's planned portions into real orders, tickets and payments with realistic timings."""
    menu = [dish for dish, qty in plan.items() for _ in range(qty)]
    rng.shuffle(menu)
    main_cats = set(MenuCategory.names_of_kind(MenuCategory.Kind.MAIN))
    mains = [d for d in menu if d.category in main_cats]
    others = [d for d in menu if d.category not in main_cats]
    tables = list(Table.objects.filter(location=outlet, is_active=True))
    weekend = day.weekday() >= 4
    orders = []
    while mains:
        party = rng.choices([1, 2, 2, 2, 3, 4, 4, 5, 6, 7], k=1)[0]
        kind = rng.choices(["dine_in", "takeout", "delivery"], [0.74, 0.14, 0.12])[0]
        size = party if kind == "dine_in" else rng.choice([1, 2, 2, 3])
        dishes = [mains.pop() for _ in range(min(size, len(mains)))]
        extra = min(len(others), round(size * rng.uniform(1.0, 2.2)))
        dishes += [others.pop() for _ in range(extra)]
        orders.append((kind, size, dishes))
    while others:  # drinks/sides-only orders, e.g. a shake to go
        orders.append(("takeout", 1, [others.pop() for _ in range(min(3, len(others)))]))
    for kind, size, dishes in orders:
        lunch = rng.random() < 0.35
        opened = _at(day, *(LUNCH if lunch else DINNER), rng)
        peak = (not lunch) and 18 <= timezone.localtime(opened).hour <= 19
        if kind == "dine_in":
            fitting = [t for t in tables if t.seats >= size] or tables
            o = services.open_order(outlet, server, table=rng.choice(fitting), guests=size,
                                    guest=rng.choice(guests) if rng.random() < 0.35 else None, at=opened)
        elif kind == "takeout":
            o = services.open_order(outlet, server, type=Order.Type.TAKEOUT, customer_name=f"{rng.choice(FIRST)}", at=opened)
        else:
            o = services.open_order(outlet, None, type=Order.Type.DELIVERY, channel=rng.choice(["uber_eats", "doordash"]),
                                    external_ref=f"D{rng.randint(10000, 99999)}", at=opened)
        for d in dishes:
            _add(o, d, 1, server, rng, stocked)
        order_wait = rng.uniform(3, 9) * (1.3 if peak else 1) if kind == "dine_in" else rng.uniform(0.2, 1)
        sent = opened + timedelta(minutes=order_wait)
        ticket = services.send_to_kitchen(o, server, at=sent)
        slow = (1.35 if peak else 1) * (1.12 if weekend else 1) * busy
        started = sent + timedelta(minutes=rng.uniform(0.5, 4) * slow)
        ready = started + timedelta(minutes=rng.uniform(7, 13) * slow)
        served = ready + timedelta(minutes=rng.uniform(0.5, 3.5) * (1.4 if peak else 1))
        services.ticket_step(ticket, "start", at=started)
        services.ticket_step(ticket, "ready", at=ready)
        services.ticket_step(ticket, "served", at=served)
        if kind == "dine_in" and o.service_charge_rate and rng.random() < 0.09:
            services.remove_service_charge(o, rng.choice(["Food was late", "Guest unhappy with service", "Didn't know about it"]))
        o.refresh_from_db()
        if kind == "delivery":
            services.take_payment(o, None, method=Payment.Method.APP, reference=o.external_ref)
        else:
            card = rng.random() < 0.82
            tip = (o.total * Decimal(str(rng.choice([0.10, 0.15, 0.15, 0.18, 0.20])))).quantize(Decimal("0.01")) \
                if kind == "dine_in" and not o.service_charge_rate else Decimal(0)
            services.take_payment(o, server, method=Payment.Method.CARD if card else Payment.Method.CASH, tip=tip,
                                  reference=f"AUTH{rng.randint(100000, 999999)}" if card else "")
        closed = served + timedelta(minutes=rng.uniform(25, 55) if kind == "dine_in" else 1)
        services.close_order(Order.objects.get(pk=o.pk), server, at=closed)

    # waitlist at dinner on busy nights
    if weekend:
        for _ in range(rng.randint(6, 12)):
            added = _at(day, time(18, 0), 120, rng)
            quoted = rng.choice([10, 15, 20, 25])
            waited = quoted * rng.uniform(0.7, 1.5)
            WaitlistEntry.objects.create(location=outlet, name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                                         phone=f"647555{rng.randint(1000, 9999)}", party_size=rng.choice([2, 2, 3, 4, 5]),
                                         quoted_minutes=quoted, added_at=added, notified_at=added + timedelta(minutes=waited - 1),
                                         seated_at=added + timedelta(minutes=waited), status=WaitlistEntry.Status.SEATED)


def live_service(outlet, server, guests, menu, rng, stocked=frozenset()):
    """A service in progress 'now': tables at every stage, an online order, people waiting, bookings tonight."""
    now = timezone.now()
    tables = list(Table.objects.filter(location=outlet).order_by("id"))
    kinds = MenuCategory.kind_map()
    mains = [m for m in menu if kinds.get(m.category) == MenuCategory.Kind.MAIN and m.category != "Kids"]
    sides = [m for m in menu if kinds.get(m.category) in (MenuCategory.Kind.SIDE, MenuCategory.Kind.DRINK)]

    def table_order(table, guests_n, minutes_ago, stage, guest=None):
        o = services.open_order(outlet, server, table=table, guests=guests_n, guest=guest, at=now - timedelta(minutes=minutes_ago))
        for _ in range(guests_n):
            _add(o, rng.choice(mains), 1, server, rng, stocked)
        _add(o, rng.choice(sides), max(1, guests_n // 2), server, rng, stocked, note="")
        if stage == "seated":
            return o
        t = services.send_to_kitchen(o, server, at=now - timedelta(minutes=minutes_ago - 5))
        if stage in ("cooking", "ready", "eating"):
            services.ticket_step(t, "start", at=now - timedelta(minutes=minutes_ago - 7))
        if stage in ("ready", "eating"):
            services.ticket_step(t, "ready", at=now - timedelta(minutes=max(1, minutes_ago - 18)))
        if stage == "eating":
            services.ticket_step(t, "served", at=now - timedelta(minutes=max(0.5, minutes_ago - 20)))
        return o

    table_order(tables[0], 2, 4, "seated")
    table_order(tables[2], 4, 14, "cooking", guest=next((g for g in guests if g.is_member), None))
    table_order(tables[4], 3, 21, "cooking")      # running late: shows red on the kitchen screen
    table_order(tables[6], 4, 26, "ready")
    table_order(tables[7], 6, 48, "eating")       # party of 6 → automatic service charge
    online = services.open_order(outlet, None, type=Order.Type.ONLINE, channel="website", customer_name="Jade Lam",
                                 customer_phone="4165550199", at=now - timedelta(minutes=6))
    _add(online, mains[0], 2, None, rng, stocked, note="")
    _add(online, sides[0], 2, None, rng, stocked, note="")
    services.send_to_kitchen(online, None, at=now - timedelta(minutes=6))

    for name, size, quoted, ago in (("Patel", 4, 20, 12), ("Nguyen", 2, 10, 3)):
        WaitlistEntry.objects.create(location=outlet, name=name, phone="6475550123", party_size=size, quoted_minutes=quoted,
                                     added_at=now - timedelta(minutes=ago))
    tonight = timezone.localdate()
    for name, size, hh, mm, table in (("Kapoor", 6, 19, 0, tables[8]), ("Evans", 2, 19, 30, None), ("Fong", 4, 20, 0, tables[3]),
                                      ("Grewal birthday", 8, 20, 30, tables[8])):
        Reservation.objects.create(location=outlet, name=name, phone="4165550100", party_size=size, table=table,
                                   starts_at=timezone.make_aware(datetime.combine(tonight, time(hh, mm))),
                                   notes="Birthday: bring a candle" if "birthday" in name else "")


POS_SERVER = ("sofia", "Sofia", "Reyes", "LarderServer1")
