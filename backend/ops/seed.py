"""Demo staffing, complaints, equipment, issues and handover notes. Called by `manage.py seed_demo`."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Complaint, DeliveryScore, Department, Employee, Equipment, HandoverNote, Issue, StaffingPlan
from .services import daily_alerts

FIRST = ["Aarav", "Priya", "Liam", "Fatima", "Noah", "Simran", "Ethan", "Mei", "Omar", "Chloe", "Arjun", "Sofia",
         "Lucas", "Harleen", "Mateo", "Aisha", "Daniel", "Nadia", "Ravi", "Grace", "Karan", "Zoe", "Yusuf", "Emma",
         "Jaspreet", "Leo", "Ananya", "Isaac", "Meera", "Hassan", "Olivia", "Dev", "Sara", "Tariq", "Maya", "Nikhil"]
LAST = ["Sharma", "Patel", "Nguyen", "Khan", "Singh", "Brown", "Wilson", "Ali", "Chen", "Gill", "Martin", "Das",
        "Garcia", "Kaur", "Thomas", "Rossi", "Ahmed", "Lee", "Mehta", "Clarke"]
POSITIONS = {
    Department.SERVICE: ["Server", "Server", "Server", "Host", "Bartender", "Busser"],
    Department.KITCHEN: ["Line cook", "Line cook", "Grill cook", "Prep cook", "Dishwasher", "Sous chef"],
    Department.DELIVERY: ["Packer", "Driver"],
    Department.MANAGEMENT: ["Restaurant manager", "Assistant manager"],
}
# location code -> department -> (required, actual)
STAFF = {
    "SQ1": {Department.SERVICE: (14, 11), Department.KITCHEN: (12, 11), Department.MANAGEMENT: (2, 2)},
    "BRM": {Department.SERVICE: (11, 8), Department.KITCHEN: (11, 9), Department.MANAGEMENT: (2, 1)},
    "OAK": {Department.SERVICE: (10, 10), Department.KITCHEN: (9, 8), Department.MANAGEMENT: (2, 2)},
    "CK": {Department.KITCHEN: (12, 6), Department.DELIVERY: (3, 3), Department.MANAGEMENT: (1, 1)},
}
COMPLAINT_RATE = {"SQ1": 0.25, "BRM": 0.55, "OAK": 0.18}  # per day
# delivery orders with a wrong or missing item, per day (Brampton's packing station is the weak spot)
WRONG_MISSING_RATE = {"SQ1": (0.18, 0.22), "BRM": (0.33, 0.45), "OAK": (0.12, 0.15)}
WRONG = ["Got the Nashville instead of the Buffalo chicken", "Single instead of double patty", "Classic fries instead of Cajun",
         "Bacon on a no-bacon burger"]
MISSING = ["Missing truffle fries", "No dips in the bag", "Oreo shake missing", "Missing one burger", "No napkins or cutlery"]
# platform -> location -> (food-ready accuracy %, rating)
DELIVERY = {"uber_eats": {"SQ1": (88, 4.6), "BRM": (79, 4.3), "OAK": (91, 4.7)},
            "doordash": {"SQ1": (85, 4.5), "BRM": (81, 4.4), "OAK": (89, 4.6)}}
COMPLAINTS = [
    ("food", "Fries were soggy by the time they arrived", "Replaced the fries"),
    ("wait", "Waited 40 minutes for mains on a Friday", "Apologised, comped dessert"),
    ("missing", "Delivery order missing onion rings", "Refunded through the app"),
    ("service", "Server didn't come back to take a drink order", "Manager spoke to the table"),
    ("food", "Patty overcooked, no crust", "Remade it"),
    ("clean", "Sticky table at the window", "Cleaned, reminded the team"),
    ("price", "Didn't expect the automatic service charge", "Explained the policy; removed it"),
    ("wrong", "Got beef instead of chicken smash", "Swapped and comped"),
]
EQUIPMENT = {
    "outlet": [("Walk-in cooler", "Refrigeration"), ("Reach-in fridge", "Refrigeration"), ("Flat-top griddle", "Cooking"),
               ("Fryer", "Cooking"), ("Dishwasher", "Dish"), ("POS terminal", "Front of house")],
    "kitchen": [("Walk-in cooler", "Refrigeration"), ("Walk-in freezer", "Refrigeration"), ("Combi oven", "Cooking"),
                ("Tilt kettle", "Cooking"), ("Delivery van", "Vehicles")],
}
NOTES = [
    ("closing", "Low on smash balls tonight. Asked the kitchen for 200 in the morning request.", False),
    ("opening", "Fryer 2 is slow to heat. Gave it 20 minutes before service; keep an eye on it.", False),
    ("closing", "Party of 18 booked for Saturday 7 pm. Pre-prep 3 L extra cheese sauce.", True),
    ("opening", "Health inspector visited at 2 pm. All good, report in the office.", True),
    ("closing", "Card terminal 2 dropped connection twice. Restarted it.", False),
    ("general", "New server Chloe starts Thursday. Pair her with Sofia for her first two shifts.", False),
]


def seed_ops(locations, manager, cook, rng):
    today = timezone.localdate()
    names = [f"{f} {last}" for f in FIRST for last in LAST]
    rng.shuffle(names)
    for loc in locations:
        for dept, (required, actual) in STAFF.get(loc.code, {}).items():
            StaffingPlan.objects.create(location=loc, department=dept, required=required, updated_by=manager)
            for i in range(actual):
                Employee.objects.create(location=loc, department=dept, name=names.pop(),
                                        position=POSITIONS[dept][i % len(POSITIONS[dept])],
                                        started_on=today - timedelta(days=rng.randint(30, 1400)))
        for dept in STAFF.get(loc.code, {}):  # a couple of leavers, so history exists
            if rng.random() < 0.5:
                Employee.objects.create(location=loc, department=dept, name=names.pop(), position=POSITIONS[dept][0],
                                        started_on=today - timedelta(days=400), left_on=today - timedelta(days=rng.randint(5, 60)),
                                        is_active=False)
        for name, category in EQUIPMENT["kitchen" if loc.kind == "kitchen" else "outlet"]:
            Equipment.objects.create(location=loc, name=name, category=category,
                                     service_contact="GTA Refrigeration, 905-555-0142" if category == "Refrigeration" else "")
        if loc.code in COMPLAINT_RATE:
            for back in range(60, 0, -1):
                if rng.random() < COMPLAINT_RATE[loc.code]:
                    cat, detail, action = rng.choice(COMPLAINTS)
                    Complaint.objects.create(location=loc, occurred_on=today - timedelta(days=back), category=cat,
                                             channel=rng.choice(["in_person", "in_person", "review", "delivery", "phone"]),
                                             detail=detail, action_taken=action, comped=Decimal(rng.choice(["0", "0", "5.45", "12.95", "17.45"])),
                                             logged_by=manager)
        if loc.code in WRONG_MISSING_RATE:
            wrong_rate, missing_rate = WRONG_MISSING_RATE[loc.code]
            for back in range(60, 0, -1):
                for cat, rate, texts in (("wrong", wrong_rate, WRONG), ("missing", missing_rate, MISSING)):
                    if rng.random() < rate:
                        Complaint.objects.create(location=loc, occurred_on=today - timedelta(days=back), category=cat,
                                                 channel="delivery", detail=rng.choice(texts), action_taken="Refunded through the app",
                                                 comped=Decimal(rng.choice(["4.95", "11.95", "15.45"])), logged_by=manager)
            monday = today - timedelta(days=today.weekday())
            for platform, by_loc in DELIVERY.items():
                acc, rating = by_loc[loc.code]
                for w in range(1, 9):
                    DeliveryScore.objects.create(
                        location=loc, platform=platform, week_start=monday - timedelta(weeks=w), orders=rng.randint(90, 160),
                        ready_accuracy=Decimal(str(round(min(99, acc + rng.uniform(-4, 4)), 1))),
                        rating=Decimal(str(round(min(5, rating + rng.uniform(-0.1, 0.1)), 2))), entered_by=manager)
        for back in (3, 2, 1):
            shift, body, important = rng.choice(NOTES)
            note = HandoverNote.objects.create(location=loc, business_date=today - timedelta(days=back), shift=shift,
                                               body=body, is_important=important, author=cook if loc.code == "BRM" else manager)
            HandoverNote.objects.filter(pk=note.pk).update(
                created_at=timezone.make_aware(datetime.combine(today - timedelta(days=back), time(22 if shift == "closing" else 11, 15))))

    # Some history: a fixed issue and an open low-priority one
    sq1 = next(loc for loc in locations if loc.code == "SQ1")
    fryer = Equipment.objects.get(location=sq1, name="Fryer")
    fixed = Issue.objects.create(location=sq1, equipment=fryer, title="Fryer thermostat not holding 175 °C",
                                 detail="Oil temperature dropping to 150 °C during rush.", severity=Issue.Severity.HIGH,
                                 status=Issue.Status.RESOLVED, assigned_to="Pro Kitchen Services", raised_by=manager,
                                 resolution="Thermostat replaced", repair_cost=285)
    Issue.objects.filter(pk=fixed.pk).update(created_at=timezone.now() - timedelta(days=12), resolved_at=timezone.now() - timedelta(days=10))
    oak = next(loc for loc in locations if loc.code == "OAK")
    Issue.objects.create(location=oak, equipment=Equipment.objects.get(location=oak, name="Dishwasher"),
                         title="Dishwasher leaking at the door", detail="Small puddle after each cycle.",
                         severity=Issue.Severity.LOW, raised_by=manager)


def finish_ops(locations_by_code):
    """After checklists exist: attach the auto-raised walk-in issue to its equipment and send alerts."""
    brm = locations_by_code.get("BRM")
    if brm:
        walk_in = Equipment.objects.filter(location=brm, name="Walk-in cooler").first()
        Issue.objects.filter(location=brm, equipment__isnull=True, title__icontains="Walk-in").update(
            equipment=walk_in, assigned_to="GTA Refrigeration", status=Issue.Status.IN_PROGRESS)
    daily_alerts()


RATES = {Department.SERVICE: (17.60, 19.50), Department.KITCHEN: (19.00, 24.00), Department.DELIVERY: (17.60, 18.50),
         Department.MANAGEMENT: (27.00, 32.00)}
LABOUR_TARGET = {"SQ1": 0.29, "BRM": 0.34, "OAK": 0.27}  # labour cost as a share of sales
DAILY_SALES = {"SQ1": 3600, "BRM": 2700, "OAK": 2300}
PIN_BASE = {"SQ1": 1001, "BRM": 2001, "OAK": 3001, "CK": 4001}
SHIFT_TIMES = {Department.SERVICE: [(time(11, 0), time(16, 0)), (time(16, 30), time(23, 0))],
               Department.KITCHEN: [(time(10, 0), time(16, 0)), (time(15, 30), time(23, 0))],
               Department.DELIVERY: [(time(9, 0), time(15, 0))], Department.MANAGEMENT: [(time(10, 0), time(19, 0))]}


def seed_labour(locations, rng, manager):
    """Hourly rates, PINs, two weeks of clock-ins sized to a realistic labour %, and this week's schedule."""
    from .models import Shift, TimeEntry

    today = timezone.localdate()
    for loc in locations:
        staff = list(Employee.objects.filter(location=loc, is_active=True).order_by("id"))
        for i, e in enumerate(staff):
            lo, hi = RATES[e.department]
            e.hourly_rate = Decimal(str(round(rng.uniform(lo, hi), 2)))
            e.shares_tips = e.department == Department.SERVICE
            if i < 3:
                e.set_pin(str(PIN_BASE[loc.code] + i))
            e.save()
        budget_rate = sum(float(e.hourly_rate) for e in staff) / len(staff)
        for back in range(14, 0, -1):
            day = today - timedelta(days=back)
            busy = 1.3 if day.weekday() >= 4 else 1.0
            hours_needed = DAILY_SALES.get(loc.code, 1500) * busy * LABOUR_TARGET.get(loc.code, 0.3) / budget_rate
            rng.shuffle(staff)
            worked = 0.0
            for e in staff:
                if worked >= hours_needed:
                    break
                start, end = rng.choice(SHIFT_TIMES[e.department])
                cin = timezone.make_aware(datetime.combine(day, start)) + timedelta(minutes=rng.randint(-8, 10))
                cout = timezone.make_aware(datetime.combine(day, end)) + timedelta(minutes=rng.randint(-10, 25))
                entry = TimeEntry.objects.create(employee=e, location=loc, clock_in=cin, clock_out=cout,
                                                 break_minutes=30 if (cout - cin).total_seconds() > 5 * 3600 else 0)
                worked += entry.hours or 0
        if loc.code == "SQ1":  # people on shift right now, for the time clock screen
            for e in staff[:4]:
                TimeEntry.objects.create(employee=e, location=loc, clock_in=timezone.now() - timedelta(minutes=rng.randint(60, 240)))
        monday = today - timedelta(days=today.weekday())
        for offset in range(14):
            day = monday + timedelta(days=offset)
            for e in rng.sample(staff, k=max(1, len(staff) * 4 // 7)):
                start, end = rng.choice(SHIFT_TIMES[e.department])
                Shift.objects.create(employee=e, location=loc, date=day, start=start, end=end, role=e.position,
                                     published=offset < 7, created_by=manager)
