"""Load a realistic demo: 3 outlets + a central kitchen running for N days.

Everything goes through the same service functions the app uses (sales imports, deliveries,
production, transfers, counts, wastage), so the ledger and reports are consistent.

    python manage.py seed_demo            # first time
    python manage.py seed_demo --reset    # wipe Larder data (keeps superusers) and reload
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditEntry
from checklists.models import SOP, ChecklistRun, ChecklistTemplate, RunAnswer
from checklists.seed import seed_checklists
from ops.models import Complaint, Employee, Equipment, HandoverNote, Issue, Notification, StaffingPlan
from ops.seed import finish_ops, seed_ops
from purchasing.models import InvoiceScan
from catalog.models import Item, Location, MenuItem, MenuLine, PriceHistory, RecipeLine, Vendor
from purchasing import services as po_services
from purchasing.models import PurchaseOrder, PurchaseOrderLine
from sales import services as sales_services
from sales.models import SalesDay, SalesLine
from stock import services as st
from stock.models import (
    Movement, ParLevel, ProductionBatch, StockCount, StockCountLine, Transfer, TransferLine, Wastage,
)

D = lambda x: Decimal(str(x))  # noqa: E731

LOCATIONS = [
    ("SQ1", "Square One", "Mississauga", "outlet"),
    ("BRM", "Downtown Brampton", "Brampton", "outlet"),
    ("OAK", "Kerr Village", "Oakville", "outlet"),
    ("CK", "Central Kitchen", "Etobicoke", "kitchen"),
]
VENDORS = {
    "peel": ("Peel Fresh Meats", 1, "Daily"),
    "gta": ("GTA Produce Co.", 1, "Mon–Sat"),
    "dairy": ("Northfield Dairy Supply", 2, "Mon, Wed, Fri"),
    "dry": ("Lakeshore Dry Goods", 2, "Tue, Fri"),
    "spice": ("Spice Route Wholesale", 3, "Thu"),
    "pack": ("Ontario Pack & Paper", 4, "Mon"),
}
# key, name, category, unit, price, vendor, shelf life (days), allergens
RAW = [
    ("chk", "Chicken thigh, boneless", "Meat", "kg", 16.00, "peel", 4, ""),
    ("lmb", "Lamb shoulder, diced", "Meat", "kg", 26.88, "peel", 4, ""),
    ("pnr", "Paneer", "Dairy", "kg", 19.88, "dairy", 10, "Dairy"),
    ("yog", "Plain yogurt 3%", "Dairy", "L", 4.25, "dairy", 14, "Dairy"),
    ("crm", "Whipping cream 35%", "Dairy", "L", 9.50, "dairy", 10, "Dairy"),
    ("btr", "Butter, unsalted", "Dairy", "kg", 15.50, "dairy", 60, "Dairy"),
    ("ghe", "Ghee", "Dairy", "kg", 22.38, "dairy", 180, "Dairy"),
    ("mlk", "Milk 2%", "Dairy", "L", 2.31, "dairy", 10, "Dairy"),
    ("ric", "Basmati rice", "Dry goods", "kg", 4.88, "dry", 365, ""),
    ("flr", "All-purpose flour", "Dry goods", "kg", 1.56, "dry", 180, "Gluten"),
    ("chp", "Chickpeas, dried", "Dry goods", "kg", 3.88, "dry", 365, ""),
    ("sug", "Sugar", "Dry goods", "kg", 1.81, "dry", 365, ""),
    ("oil", "Canola oil", "Dry goods", "L", 4.00, "dry", 270, ""),
    ("mng", "Mango pulp", "Dry goods", "L", 6.38, "dry", 365, ""),
    ("onn", "Yellow onion", "Produce", "kg", 2.00, "gta", 21, ""),
    ("tom", "Roma tomato", "Produce", "kg", 3.88, "gta", 7, ""),
    ("grl", "Garlic, peeled", "Produce", "kg", 9.25, "gta", 14, ""),
    ("gng", "Ginger root", "Produce", "kg", 7.75, "gta", 21, ""),
    ("cil", "Cilantro", "Produce", "kg", 13.13, "gta", 5, ""),
    ("lem", "Lemon", "Produce", "pc", 0.65, "gta", 21, ""),
    ("pot", "Russet potato", "Produce", "kg", 1.63, "gta", 30, ""),
    ("spn", "Spinach", "Produce", "kg", 8.00, "gta", 5, ""),
    ("gmr", "Garam masala", "Spices", "kg", 38.75, "spice", 365, ""),
    ("kch", "Kashmiri chili powder", "Spices", "kg", 30.63, "spice", 365, ""),
    ("trm", "Turmeric powder", "Spices", "kg", 23.75, "spice", 365, ""),
    ("cmn", "Cumin seed", "Spices", "kg", 20.63, "spice", 365, ""),
    ("box", "Takeout container 32 oz", "Packaging", "pc", 0.43, "pack", None, ""),
]
PREPS = [
    ("mkh", "Makhani gravy", "L", 4, 40, [("tom", .62), ("btr", .07), ("crm", .10), ("onn", .15), ("grl", .025),
                                          ("gng", .025), ("kch", .012), ("gmr", .006), ("sug", .012)]),
    ("mar", "Tandoori marinade", "kg", 3, 12, [("yog", .62), ("grl", .05), ("gng", .05), ("kch", .03), ("gmr", .015),
                                               ("trm", .01), ("lem", 2), ("oil", .05)]),
    ("dgh", "Naan dough", "kg", 2, 30, [("flr", .6), ("yog", .1), ("mlk", .16), ("sug", .02), ("ghe", .03)]),
    ("msl", "Onion-tomato masala", "kg", 4, 25, [("onn", .55), ("tom", .42), ("oil", .07), ("grl", .03), ("gng", .03),
                                                 ("cmn", .01), ("trm", .005), ("gmr", .01)]),
]
# pos code, name, category, price, popularity, recipe
MENU = [
    ("BC01", "Butter Chicken", "Mains", 22.95, 1.0, [("chk", .22), ("mar", .04), ("mkh", .26), ("crm", .025), ("btr", .012), ("cil", .003), ("box", .35)]),
    ("CT01", "Chicken Tikka", "Starters", 16.95, .55, [("chk", .24), ("mar", .08), ("lem", .5), ("oil", .012), ("onn", .04)]),
    ("RJ01", "Lamb Rogan Josh", "Mains", 26.95, .32, [("lmb", .24), ("msl", .2), ("yog", .04), ("kch", .004), ("ghe", .018), ("box", .35)]),
    ("PM01", "Paneer Makhani", "Mains", 20.95, .6, [("pnr", .18), ("mkh", .26), ("crm", .025), ("btr", .012), ("box", .35)]),
    ("PP01", "Palak Paneer", "Mains", 19.95, .28, [("spn", .3), ("pnr", .14), ("msl", .09), ("crm", .025), ("box", .35)]),
    ("CM01", "Chana Masala", "Mains", 16.95, .45, [("chp", .1), ("msl", .16), ("cil", .004), ("lem", .25), ("box", .35)]),
    ("BN01", "Butter Naan", "Breads", 3.95, 1.6, [("dgh", .12), ("btr", .01)]),
    ("GN01", "Garlic Naan", "Breads", 4.75, 1.2, [("dgh", .12), ("grl", .008), ("btr", .012), ("cil", .002)]),
    ("JR01", "Jeera Rice", "Sides", 6.95, .9, [("ric", .13), ("cmn", .003), ("ghe", .01), ("box", .35)]),
    ("CB01", "Chicken Biryani", "Mains", 23.95, .7, [("ric", .17), ("chk", .2), ("mar", .05), ("msl", .08), ("ghe", .022), ("onn", .06), ("cil", .004), ("box", .35)]),
    ("AT01", "Aloo Tikki Chaat", "Starters", 12.95, .22, [("pot", .2), ("chp", .03), ("yog", .07), ("cil", .004), ("oil", .035)]),
    ("ML01", "Mango Lassi", "Drinks", 6.95, .65, [("mng", .13), ("yog", .2), ("sug", .015), ("mlk", .06)]),
    ("CH01", "Masala Chai", "Drinks", 3.95, .55, [("mlk", .18), ("sug", .012), ("gng", .003)]),
    ("GJ01", "Gulab Jamun", "Desserts", 6.95, .38, [("mlk", .1), ("sug", .05), ("ghe", .02), ("flr", .02)]),
    ("KF01", "Mango Kulfi", "Desserts", 7.50, .26, [("mlk", .15), ("mng", .04), ("sug", .03), ("crm", .03)]),
]
BRAND = "Saffron Lane"
# How much each outlet grew vs last year (drives SSSG); and how often guests ask to remove service charge
GROWTH = {"SQ1": 0.17, "BRM": 0.05, "OAK": 0.11}
SC_REMOVED = {"SQ1": 0.09, "BRM": 0.21, "OAK": 0.07}
HISTORY_DAYS = 455  # ~15 months, so quarter-on-quarter-last-year works
DOW = [0.8, 0.82, 0.9, 1.0, 1.32, 1.42, 1.12]  # Mon..Sun
OUTLET_SIZE = {"SQ1": 1.25, "BRM": 0.95, "OAK": 0.8}
# Share of real usage that disappears without a record (over-portioning, theft, bad receiving)
LOSS = {"chk": .085, "lmb": .06, "pnr": .11, "crm": .16, "btr": .07, "ghe": .19, "mkh": .05, "mar": .045,
        "dgh": .07, "msl": .035, "ric": .04, "cil": .24, "spn": .15, "yog": .03, "box": .05}
LOSS_BY_OUTLET = {"SQ1": 1.15, "BRM": 2.2, "OAK": 0.85, "CK": 0.4}
# Late price rises so alerts have something to say
PRICE_JUMPS = {"chk": 1.086, "crm": 1.063, "tom": 1.108}
USERS = [
    ("owner", "Sam", "Owner", Role.OWNER, [], "LarderOwner1"),
    ("meera", "Meera", "Shah", Role.MANAGER, ["SQ1", "BRM", "OAK", "CK"], "LarderManager1"),
    ("ravi", "Ravi", "Kumar", Role.COOK, ["BRM"], "LarderCook1"),
    ("ana", "Ana", "Lopez", Role.COOK, ["CK"], "LarderCook1"),
]


class Command(BaseCommand):
    help = "Load realistic demo data for Larder (3 outlets + central kitchen)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--reset", action="store_true", help="Delete existing Larder data first")
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, days, reset, seed, **kwargs):
        if Location.objects.exists():
            if not reset:
                raise CommandError("Data already exists. Run with --reset to wipe it and load the demo again.")
            self.wipe()
        self.rng = random.Random(seed)
        with transaction.atomic():
            self.build(days)
        self.stdout.write(self.style.SUCCESS("Demo data loaded. Log in with:"))
        for username, *_, role, _, password in USERS:
            self.stdout.write(f"  {username:<6} / {password:<15} ({role.label})")

    # ------------------------------------------------------------------

    def wipe(self):
        self.stdout.write("Removing existing Larder data…")
        for model in [Notification, Issue, Equipment, HandoverNote, Complaint, Employee, StaffingPlan, InvoiceScan,
                      AuditEntry, RunAnswer, ChecklistRun, ChecklistTemplate, SOP, SalesLine, SalesDay, PurchaseOrderLine, PurchaseOrder, Movement, StockCountLine,
                      StockCount, Wastage, TransferLine, Transfer, ProductionBatch, ParLevel, PriceHistory, MenuLine,
                      MenuItem, RecipeLine]:
            model.objects.all().delete()
        Item.objects.all().delete()
        Vendor.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Location.objects.all().delete()

    def build(self, days):
        rng = self.rng
        today = timezone.localdate()
        start = today - timedelta(days=days)

        self.loc = {code: Location.objects.create(code=code, name=n, city=c, kind=k, brand=BRAND if k == "outlet" else "")
                    for code, n, c, k in LOCATIONS}
        outlets = [self.loc[c] for c in OUTLET_SIZE]
        ck = self.loc["CK"]
        vendors = {k: Vendor.objects.create(name=n, lead_days=lead, delivery_days=dd) for k, (n, lead, dd) in VENDORS.items()}

        # Start prices a bit lower and drift up to today's list, so price history looks real.
        self.item = {}
        for key, name, cat, unit, price, v, shelf, allergens in RAW:
            start_price = D(price) / D(PRICE_JUMPS.get(key, 1)) / D(1 + rng.uniform(0.0, 0.03))
            self.item[key] = Item.objects.create(
                name=name, category=cat, unit=unit, kind=Item.Kind.RAW, vendor=vendors[v],
                last_price=st.q4(start_price), shelf_life_days=shelf, allergens=allergens,
            )
        self.target_price = {key: D(price) for key, _, _, _, price, *_ in RAW}
        for key, name, unit, shelf, batch, recipe in PREPS:
            prep = Item.objects.create(name=name, category="Prep", unit=unit, kind=Item.Kind.PREP,
                                       shelf_life_days=shelf, batch_size=D(batch))
            self.item[key] = prep
            RecipeLine.objects.bulk_create(RecipeLine(prep=prep, component=self.item[c], qty=D(q)) for c, q in recipe)
        self.menu = []
        for code, name, cat, price, pop, recipe in MENU:
            dish = MenuItem.objects.create(pos_code=code, name=name, category=cat, price=D(price))
            MenuLine.objects.bulk_create(MenuLine(menu_item=dish, item=self.item[c], qty=D(q)) for c, q in recipe)
            self.menu.append((dish, pop, recipe))

        users = {}
        for username, first, last, role, locs, password in USERS:
            u = User.objects.create_user(username=username, password=password, first_name=first, last_name=last, role=role)
            u.locations.set([self.loc[c] for c in locs])
            users[username] = u
        self.manager, self.cook, self.ck_cook = users["meera"], users["ravi"], users["ana"]

        # Par levels from expected daily usage × (lead time + 2 days of cover)
        daily = {o.code: {} for o in outlets}
        for o in outlets:
            for _dish, pop, recipe in self.menu:
                portions = 22 * pop * OUTLET_SIZE[o.code]
                for key, q in recipe:
                    daily[o.code][key] = daily[o.code].get(key, 0) + portions * q
        ck_daily = {}
        for key, *_rest, recipe in [(p[0], p[5]) for p in PREPS]:
            made = sum(daily[o][key] for o in daily if key in daily[o])
            for comp, q in recipe:
                ck_daily[comp] = ck_daily.get(comp, 0) + made * q
        self.pars = {}
        for o in outlets:
            pars = []
            for key, use in daily[o.code].items():
                item = self.item[key]
                lead = 1 if item.kind == Item.Kind.PREP else item.vendor.lead_days
                pars.append((item, st.round_up(D(use * (lead + 2)), item.unit)))
            st.set_pars(o, pars, self.manager)
            self.pars[o.code] = dict((i.id, p) for i, p in pars)
        ck_pars = [(self.item[k], st.round_up(D(u * (self.item[k].vendor.lead_days + 3)), self.item[k].unit)) for k, u in ck_daily.items()]
        ck_pars += [(self.item[p[0]], st.round_up(D(sum(daily[o].get(p[0], 0) for o in daily) * 2), p[2])) for p in PREPS]
        st.set_pars(ck, ck_pars, self.manager)
        self.pars["CK"] = dict((i.id, p) for i, p in ck_pars)

        # Opening stock the day before the period starts
        for loc in [*outlets, ck]:
            for item_id, par in self.pars[loc.code].items():
                item = Item.objects.get(pk=item_id)
                st.record(loc, item, Movement.Kind.OPENING, par * D("1.1"), self.manager, "OPENING", start - timedelta(days=1))

        self.usage_since_count = {loc.code: {} for loc in [*outlets, ck]}
        item_mult = {o.code: [rng.uniform(.82, 1.18) for _ in self.menu] for o in outlets}
        item_mult["OAK"][2] = 1.55  # Oakville loves the lamb
        item_mult["BRM"][5] = 1.35  # Brampton sells more chana

        self.stdout.write(f"  importing {HISTORY_DAYS} days of past sales…")
        self.history(outlets, start, item_mult)
        seed_ops([*outlets, ck], self.manager, self.cook, rng)

        for n in range(days):
            day = start + timedelta(days=n)
            self.drift_prices(n, days, day)
            self.deliveries(day, [*outlets, ck])
            self.kitchen_day(day, ck, outlets)
            for o in outlets:
                self.sell(o, day, n, item_mult[o.code])
                if rng.random() < 0.18:
                    self.waste(o, day)
            if rng.random() < 0.12:
                self.waste(ck, day)
            if day.weekday() == 6:  # Sunday-night counts
                for loc in [*outlets, ck]:
                    self.count(loc, day)

        self.open_state(today, ck, outlets)
        photos = seed_checklists([*outlets, ck], self.manager, {"BRM": self.cook, "CK": self.ck_cook}, rng, min(days, 7))
        self.stdout.write(f"  checklists: 4 templates, a week of runs, {photos} demo photos")
        finish_ops(self.loc)
        self.stdout.write(f"  {Movement.objects.count():,} ledger entries over {days} days")

    # ------------------------------------------------------------------

    def drift_prices(self, n, days, day):
        """Move each raw price a step toward today's list price; jumps land in the last week."""
        for key, item in self.item.items():
            if item.kind != Item.Kind.RAW:
                continue
            item.refresh_from_db(fields=["last_price"])
            target = self.target_price[key]
            if key in PRICE_JUMPS:
                before = target / D(PRICE_JUMPS[key])
                goal = before if n < days - 6 else target
            else:
                goal = target
            if item.last_price != goal and (n % 7 == 0 or n == days - 6):
                remaining = max(1, (days - n) // 7)
                item.last_price = st.q4(item.last_price + (goal - item.last_price) / remaining)
                item.save(update_fields=["last_price"])

    def deliveries(self, day, locations):
        rng = self.rng
        for loc in locations:
            stock = st.on_hand_map(loc)
            by_vendor = {}
            for item_id, par in self.pars[loc.code].items():
                item = self.item_by_id(item_id)
                if item.kind != Item.Kind.RAW:
                    continue
                if stock.get(item_id, 0) < par * D("0.6"):
                    qty = st.round_up(par * D("1.4") - stock.get(item_id, 0), item.unit)
                    by_vendor.setdefault(item.vendor, []).append((item, qty, None))
            for vendor, lines in by_vendor.items():
                po = po_services.create_order(vendor, loc, lines, self.manager, on=day - timedelta(days=vendor.lead_days))
                po_services.send_order(po, on=day - timedelta(days=vendor.lead_days))
                received = {}
                for line in po.lines.all():
                    # Occasionally a short delivery
                    qty = line.qty * D("0.9") if rng.random() < 0.04 else line.qty
                    # invoiced at today's price, which may have moved since the order was placed
                    received[line.id] = (qty, self.item_by_id(line.item_id).last_price)
                po_services.receive_order(po, received, self.cook if loc.kind == "outlet" else self.ck_cook,
                                          invoice_number=f"INV-{rng.randint(20000, 99999)}", on=day)

    def kitchen_day(self, day, ck, outlets):
        rng = self.rng
        # 1. What do outlets need?
        needs = {}
        for o in outlets:
            stock = st.on_hand_map(o)
            for key, *_ in PREPS:
                item = self.item[key]
                par = self.pars[o.code].get(item.id)
                if par and stock.get(item.id, 0) < par:
                    needs.setdefault(o, []).append((item, st.round_up(par * D("1.1") - stock.get(item.id, 0), item.unit)))
        # 2. Cook enough to cover it
        ck_stock = st.on_hand_map(ck)
        for key, *_ in PREPS:
            item = self.item[key]
            want = sum((q for lines in needs.values() for i, q in lines if i == item), D(0))
            short = want - ck_stock.get(item.id, 0) + self.pars["CK"][item.id] * D("0.3")
            if short > 0:
                qty = st.round_up(short, item.unit)
                batch = ProductionBatch.objects.create(location=ck, item=item, qty=qty, planned_for=day, created_by=self.manager)
                try:
                    st.complete_batch(batch, self.ck_cook, on=day)
                except Exception:  # not enough raw stock today: leave it planned
                    batch.delete()
        # 3. Send it out
        for o, lines in needs.items():
            t = st.request_transfer(ck, o, lines, self.cook, on=day)
            stock = st.on_hand_map(ck)
            sent = {line.id: min(line.qty_requested, max(D(0), stock.get(line.item_id, D(0)))) for line in t.lines.all()}
            if not any(sent.values()):
                t.status = Transfer.Status.CANCELLED
                t.save(update_fields=["status"])
                continue
            st.dispatch_transfer(t, sent, self.ck_cook, on=day)
            received = {}
            for line in t.lines.all():
                received[line.id] = line.qty_sent * D("0.9") if rng.random() < 0.05 else line.qty_sent
            st.receive_transfer(t, received, self.cook, on=day)

    def sell(self, outlet, day, n, mult):
        rng = self.rng
        lines = []
        for i, (dish, pop, recipe) in enumerate(self.menu):
            qty = round(22 * pop * OUTLET_SIZE[outlet.code] * mult[i] * DOW[day.weekday()] * (1 + 0.004 * n) * rng.uniform(.86, 1.14))
            if qty <= 0:
                continue
            lines.append((dish, qty, (dish.price * qty).quantize(D("0.01"))))
            for key, q in recipe:
                self.usage_since_count[outlet.code][key] = self.usage_since_count[outlet.code].get(key, 0) + qty * q
        sales_services.import_day(outlet, day, lines, self.manager, source="Toast POS" if outlet.code == "SQ1" else "Square POS",
                                  totals=self.day_totals(outlet, lines))

    def day_totals(self, outlet, lines):
        """Covers ≈ mains and biryani portions plus a share of starters; bills ≈ party of 2.3."""
        rng = self.rng
        mains = sum(q for dish, q, _ in lines if dish.category == "Mains")
        starters = sum(q for dish, q, _ in lines if dish.category == "Starters")
        covers = round((mains * 1.08 + starters * 0.25) * rng.uniform(0.95, 1.05))
        bills = max(1, round(covers / rng.uniform(2.1, 2.5)))
        sc_bills = round(bills * rng.uniform(0.10, 0.16))  # large parties get an automatic service charge
        removed = sum(1 for _ in range(sc_bills) if rng.random() < SC_REMOVED[outlet.code])
        return {"covers": covers, "bills": bills, "sc_bills": sc_bills, "sc_removed": removed}

    def history(self, outlets, start, item_mult):
        """Past POS sales for trends and year-on-year growth. No stock usage: Larder wasn't running then."""
        rng = self.rng
        for o in outlets:
            for back in range(HISTORY_DAYS, 0, -1):
                day = start - timedelta(days=back)
                # last year's sales were lower by the outlet's growth rate, rising gently toward today
                level = (1 / (1 + GROWTH[o.code])) * (1 + GROWTH[o.code] * max(0, 364 - back) / 364)
                season = 1 + 0.06 * (1 if day.month in (11, 12) else -1 if day.month in (1, 2) else 0)
                lines = []
                for i, (dish, pop, _) in enumerate(self.menu):
                    qty = round(22 * pop * OUTLET_SIZE[o.code] * item_mult[o.code][i] * DOW[day.weekday()] * level * season
                                * rng.uniform(.86, 1.14))
                    if qty > 0:
                        lines.append((dish, qty, (dish.price * qty).quantize(D("0.01"))))
                sales_services.import_day(o, day, lines, self.manager, source="History import",
                                          totals=self.day_totals(o, lines), history=True)

    def waste(self, loc, day):
        rng = self.rng
        options = [("cil", 0.4, 1.0, "spoiled"), ("spn", 0.5, 1.5, "spoiled"), ("dgh", 1.5, 4, "overprep"),
                   ("crm", 0.5, 1.5, "expired"), ("chk", 1, 2.5, "dropped"), ("mkh", 1, 3, "quality"), ("tom", 2, 6, "spoiled")]
        stock = st.on_hand_map(loc)
        options = [o for o in options if stock.get(self.item[o[0]].id, 0) > o[2]]
        if not options:
            return
        key, lo, hi, reason = rng.choice(options)
        item = self.item[key]
        st.log_wastage(loc, item, st.round_up(D(rng.uniform(lo, hi)), item.unit), reason, self.cook, occurred_on=day)

    def count(self, loc, day):
        rng = self.rng
        stock = st.on_hand_map(loc, as_of=day)
        lines = []
        for item_id in self.pars[loc.code]:
            item = self.item_by_id(item_id)
            key = next(k for k, v in self.item.items() if v.id == item_id)
            used = D(self.usage_since_count[loc.code].get(key, 0))
            loss = used * D(LOSS.get(key, rng.uniform(.01, .03))) * D(LOSS_BY_OUTLET[loc.code]) * D(rng.uniform(.8, 1.2))
            counted = max(D(0), stock.get(item_id, D(0)) - loss)
            lines.append((item, st.q4(counted)))
        st.post_count(loc, lines, self.cook if loc.kind == "outlet" else self.ck_cook, counted_on=day, note="Weekly count")
        self.usage_since_count[loc.code] = {}

    def open_state(self, today, ck, outlets):
        """Leave some work in progress so every screen has something to act on."""
        brm = self.loc["BRM"]
        picks = po_services.reorder_suggestions(brm)[:4]
        if picks:
            po_services.orders_from_suggestions(brm, [(self.item_by_id(p["item"]), D(p["suggested"])) for p in picks], self.manager)
        spice = Vendor.objects.get(name="Spice Route Wholesale")
        po = po_services.create_order(spice, ck, [(self.item["gmr"], D(2), None), (self.item["kch"], D(2), None)],
                                      self.manager, on=today - timedelta(days=4))
        po_services.send_order(po, on=today - timedelta(days=4))  # expected 1 day ago: shows as late
        st.request_transfer(ck, brm, [(self.item["dgh"], D(12)), (self.item["mar"], D(5))], self.cook, on=today)
        for key, qty in (("dgh", 30), ("msl", 25), ("mar", 12)):
            ProductionBatch.objects.create(location=ck, item=self.item[key], qty=D(qty), planned_for=today, created_by=self.manager)

    _by_id = None

    def item_by_id(self, item_id):
        if self._by_id is None:
            self._by_id = {i.id: i for i in self.item.values()}
        item = self._by_id[item_id]
        item.refresh_from_db(fields=["last_price"])
        return item
