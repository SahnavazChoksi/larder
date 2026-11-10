"""Demo staffing, complaints, equipment, issues and handover notes. Called by `manage.py seed_demo`."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Complaint, Department, Employee, Equipment, HandoverNote, Issue, StaffingPlan
from .services import daily_alerts

FIRST = ["Aarav", "Priya", "Liam", "Fatima", "Noah", "Simran", "Ethan", "Mei", "Omar", "Chloe", "Arjun", "Sofia",
         "Lucas", "Harleen", "Mateo", "Aisha", "Daniel", "Nadia", "Ravi", "Grace", "Karan", "Zoe", "Yusuf", "Emma",
         "Jaspreet", "Leo", "Ananya", "Isaac", "Meera", "Hassan", "Olivia", "Dev", "Sara", "Tariq", "Maya", "Nikhil"]
LAST = ["Sharma", "Patel", "Nguyen", "Khan", "Singh", "Brown", "Wilson", "Ali", "Chen", "Gill", "Martin", "Das",
        "Garcia", "Kaur", "Thomas", "Rossi", "Ahmed", "Lee", "Mehta", "Clarke"]
POSITIONS = {
    Department.SERVICE: ["Server", "Server", "Server", "Host", "Bartender", "Busser"],
    Department.KITCHEN: ["Line cook", "Line cook", "Tandoor chef", "Prep cook", "Dishwasher", "Sous chef"],
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
COMPLAINTS = [
    ("food", "Butter chicken was lukewarm", "Replaced the dish"),
    ("wait", "Waited 40 minutes for mains on a Friday", "Apologised, comped dessert"),
    ("accuracy", "Delivery order missing garlic naan", "Refunded through the app"),
    ("service", "Server didn't come back to take a drink order", "Manager spoke to the table"),
    ("food", "Biryani too salty", "Remade it"),
    ("clean", "Sticky table at the window", "Cleaned, reminded the team"),
    ("price", "Didn't expect the automatic service charge", "Explained the policy; removed it"),
    ("accuracy", "Got paneer makhani instead of palak paneer", "Swapped and comped"),
]
EQUIPMENT = {
    "outlet": [("Walk-in cooler", "Refrigeration"), ("Reach-in fridge", "Refrigeration"), ("Tandoor oven", "Cooking"),
               ("Fryer", "Cooking"), ("Dishwasher", "Dish"), ("POS terminal", "Front of house")],
    "kitchen": [("Walk-in cooler", "Refrigeration"), ("Walk-in freezer", "Refrigeration"), ("Combi oven", "Cooking"),
                ("Tilt kettle", "Cooking"), ("Delivery van", "Vehicles")],
}
NOTES = [
    ("closing", "Low on garlic naan dough tonight. Asked the kitchen for 12 kg in the morning request.", False),
    ("opening", "Fryer 2 is slow to heat. Gave it 20 minutes before service; keep an eye on it.", False),
    ("closing", "Party of 18 booked for Saturday 7 pm. Pre-prep 3 L extra makhani.", True),
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
                                             detail=detail, action_taken=action, comped=Decimal(rng.choice(["0", "0", "6.95", "12.50", "22.95"])),
                                             logged_by=manager)
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
