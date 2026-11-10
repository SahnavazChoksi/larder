"""Demo SOPs, checklists and a week of completed runs. Called by `manage.py seed_demo`."""
import io
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from . import services
from .models import SOP, ChecklistRun, ChecklistTemplate, TemplateTask

SOPS = {
    "cooler": ("Walk-in and fridge temperature check", "Food safety", """Read the thermometer inside the unit, not the door display.
Walk-ins and fridges must be 0–4 °C. Freezers must be −18 °C or colder.
If a fridge is 5–7 °C, move high-risk food (meat, dairy, cooked rice) to another unit and tell the manager.
If it is above 7 °C, or food has been above 4 °C for more than 2 hours, discard high-risk food and log it as wastage.
Take a photo of the thermometer reading."""),
    "hands": ("Hand sink and sanitizer setup", "Food safety", """Each hand sink has soap, paper towel and hot water. Nothing else goes in a hand sink.
Fill sanitizer buckets to the line and test with a strip: 200 ppm quat.
Change sanitizer water every 4 hours or when dirty."""),
    "fryer": ("Fryer oil test and change", "Equipment", """Turn the fryer off and let oil cool below 50 °C before touching it.
Test oil with a test strip. Change it if the strip reads 'change' or oil smells burnt or foams.
Filter oil at the end of every shift. Wipe the outside of the fryer."""),
    "floor": ("Floor and drain cleaning", "Cleaning", """Sweep under all equipment, including behind the griddle and fryers.
Mop with degreaser, then rinse.
Lift drain covers and clear food debris. Pour hot water down each drain.
Take a photo of the kitchen floor from the pass."""),
    "cash": ("Cash drawer close-out", "Cash", """Print the POS end-of-day report.
Count the drawer with a second person. Leave the $200 float.
Enter the difference between counted cash and the POS report as cash over/short.
Put the deposit in the safe in a sealed bag, labelled with the date and your name."""),
    "lockup": ("Closing lock-up", "Security", """Check washrooms, walk-in and storage rooms are empty.
Turn off griddle, fryers and hood fans.
Lock the back door first, then the front.
Set the alarm and photograph the keypad showing 'Armed'."""),
    "label": ("Labelling and dating food", "Food safety", """Every container gets a label: item, date made, use-by date, your initials.
Prep from the central kitchen keeps its batch number.
First in, first out: newest stock goes behind older stock."""),
}

# text, sop, photo, (label, unit, min, max), critical
TEMPLATES = [
    ("Outlet opening", "opening", "outlet", time(11, 0), [
        ("Walk-in cooler at 0–4 °C", "cooler", True, ("Walk-in temperature", "°C", 0, 4), True),
        ("Reach-in fridges at 0–4 °C", "cooler", False, ("Reach-in temperature", "°C", 0, 4), True),
        ("Hand sinks stocked, sanitizer buckets ready", "hands", False, None, False),
        ("Prep levels checked against par; prep requested from kitchen if short", None, False, None, False),
        ("Hot-holding units at 60 °C or above", None, False, ("Hot-holding temperature", "°C", 60, None), True),
        ("Dining room clean and tables set", None, True, None, False),
        ("POS and card terminals working", None, False, None, False),
    ]),
    ("Outlet closing", "closing", "outlet", None, [
        ("Walk-in cooler at 0–4 °C", "cooler", True, ("Walk-in temperature", "°C", 0, 4), True),
        ("All food labelled, dated and covered", "label", True, None, True),
        ("Fryer oil tested, filtered or changed", "fryer", False, None, False),
        ("Floors mopped, drains cleared", "floor", True, None, False),
        ("Cash counted, deposit in safe", "cash", False, ("Cash over/short", "$", -5, 5), True),
        ("Griddle, fryers and hoods off", "lockup", False, None, True),
        ("Doors locked, alarm set", "lockup", True, None, True),
    ]),
    ("Kitchen opening", "opening", "kitchen", time(7, 30), [
        ("Walk-in cooler at 0–4 °C", "cooler", True, ("Walk-in temperature", "°C", 0, 4), True),
        ("Freezer at −18 °C or colder", "cooler", False, ("Freezer temperature", "°C", None, -18), True),
        ("Today's production plan checked against ingredient stock", None, False, None, False),
        ("Prep surfaces sanitized", "hands", False, None, False),
    ]),
    ("Kitchen closing", "closing", "kitchen", None, [
        ("Today's batches labelled with batch number and date", "label", True, None, True),
        ("Walk-in cooler at 0–4 °C", "cooler", False, ("Walk-in temperature", "°C", 0, 4), True),
        ("Dish area and floors cleaned", "floor", True, None, False),
        ("Doors locked, alarm set", "lockup", True, None, True),
    ]),
]

COLORS = [(52, 84, 74), (88, 70, 52), (60, 72, 96), (84, 60, 60), (70, 84, 56)]


def _photo(lines, rng) -> ContentFile:
    """A plain placeholder image so demo runs have something to show. Real runs use phone photos."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (480, 360), rng.choice(COLORS))
    draw = ImageDraw.Draw(img)
    try:
        big, small = ImageFont.load_default(size=26), ImageFont.load_default(size=18)
    except TypeError:  # Pillow < 10.1
        big = small = ImageFont.load_default()
    draw.rectangle((0, 0, 480, 44), fill=(0, 0, 0))
    draw.text((16, 10), "DEMO PHOTO", fill=(255, 255, 255), font=small)
    y = 120
    for i, line in enumerate(lines):
        line = line.replace("–", "-").replace("−", "-")  # the built-in font has no en dash
        draw.text((24, y), line, fill=(255, 255, 255), font=big if i == 0 else small)
        y += 40 if i == 0 else 28
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return ContentFile(buf.getvalue(), name="demo.jpg")


def _value(label, lo, hi, rng):
    if "Freezer" in label:
        return Decimal(str(round(rng.uniform(-22, -19), 1)))
    if "Hot-holding" in label:
        return Decimal(str(round(rng.uniform(62, 70), 1)))
    if "Cash" in label:
        return Decimal(str(rng.choice([0, 0, 0, -1.5, 2, 0.25, -0.75])))
    return Decimal(str(round(rng.uniform(1.5, 3.8), 1)))


def seed_checklists(locations, manager, cooks, rng, days=7) -> int:
    sops = {}
    for key, (title, cat, body) in SOPS.items():
        sops[key] = SOP.objects.create(title=title, category=cat, body=body, updated_by=manager)
    templates = []
    for name, kind, applies, due, tasks in TEMPLATES:
        t = ChecklistTemplate.objects.create(name=name, kind=kind, applies_to=applies, due_by=due, updated_by=manager)
        for pos, (text, sop, photo, reading, critical) in enumerate(tasks):
            label, unit, lo, hi = reading or ("", "", None, None)
            TemplateTask.objects.create(
                template=t, position=pos, text=text, sop=sops.get(sop), requires_photo=photo, value_label=label,
                value_unit=unit, value_min=lo, value_max=hi, is_critical=critical,
            )
        templates.append(t)

    today = timezone.localdate()
    photos = 0
    for n in range(days, 0, -1):
        day = today - timedelta(days=n)
        for loc in locations:
            cook = cooks.get(loc.code, manager)
            for t in templates:
                if not t.applies(loc):
                    continue
                if loc.code == "BRM" and t.kind == "closing" and n == 1:
                    continue  # missed closing: the dashboard should catch this
                run = services.start_run(t, loc, day, cook)
                warm = loc.code == "BRM" and t.kind == "closing" and n == 2
                for a in run.answers.select_related("task"):
                    task = a.task
                    value = None
                    if task.value_label:
                        value = Decimal("6.5") if warm and "Walk-in" in task.value_label else _value(task.value_label, task.value_min, task.value_max, rng)
                    photo = None
                    if task.requires_photo:
                        photo = _photo([task.text[:34], loc.name, f"{day:%a %b %d}"], rng)
                        photos += 1
                    note = "Door seal looks worn, cooler struggling" if warm and "Walk-in" in task.value_label else ""
                    services.update_answer(a, cook, done=True, value=value, note=note, photo=photo)
                services.submit_run(run, cook)
                hour = 10 if t.kind == "opening" else 23
                stamp = timezone.make_aware(datetime.combine(day, time(hour, rng.randint(5, 50))))
                ChecklistRun.objects.filter(pk=run.pk).update(started_at=stamp - timedelta(minutes=25), submitted_at=stamp)
                if n > 1:
                    if warm:
                        services.review_run(run, manager, "flag", "Walk-in at 6.5 °C. Book a repair for the door seal and move meat to the reach-in.")
                    else:
                        services.review_run(run, manager, "approve")
                    ChecklistRun.objects.filter(pk=run.pk).update(reviewed_at=stamp + timedelta(hours=9))

    # Today: Square One has started opening but isn't finished
    sq1 = next((loc for loc in locations if loc.code == "SQ1"), None)
    if sq1:
        run = services.start_run(templates[0], sq1, today, manager)
        for a in list(run.answers.select_related("task"))[:3]:
            value = _value(a.task.value_label, None, None, rng) if a.task.value_label else None
            photo = _photo([a.task.text[:34], sq1.name, "Today"], rng) if a.task.requires_photo else None
            photos += 1 if photo else 0
            services.update_answer(a, manager, done=True, value=value, photo=photo)
    return photos
