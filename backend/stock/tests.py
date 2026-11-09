"""Core ledger tests. Run with:  python manage.py test"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from catalog.models import Item, Location, MenuItem, MenuLine, RecipeLine, Vendor
from purchasing import services as po
from reports import services as reports
from sales import services as sales

from . import services as st
from .models import ProductionBatch

D = Decimal


class LedgerTests(TestCase):
    def setUp(self):
        self.outlet = Location.objects.create(code="O1", name="Outlet", kind="outlet")
        self.kitchen = Location.objects.create(code="CK", name="Kitchen", kind="kitchen")
        self.vendor = Vendor.objects.create(name="Veg Co", lead_days=1)
        self.tomato = Item.objects.create(name="Tomato", category="Produce", unit="kg", vendor=self.vendor, last_price=D("3"))
        self.cream = Item.objects.create(name="Cream", category="Dairy", unit="L", vendor=self.vendor, last_price=D("8"))
        self.gravy = Item.objects.create(name="Gravy", category="Prep", unit="L", kind="prep")
        RecipeLine.objects.create(prep=self.gravy, component=self.tomato, qty=D("0.5"))
        RecipeLine.objects.create(prep=self.gravy, component=self.cream, qty=D("0.25"))
        self.dish = MenuItem.objects.create(pos_code="D1", name="Dish", category="Mains", price=D("20"))
        MenuLine.objects.create(menu_item=self.dish, item=self.gravy, qty=D("0.2"))
        self.user = User.objects.create_user("m", password="x" * 10, role=Role.MANAGER)

    def test_prep_cost_rolls_up(self):
        self.assertEqual(self.gravy.unit_cost(), D("3.5"))  # 0.5×3 + 0.25×8
        self.assertEqual(self.dish.plate_cost(), D("0.7"))

    def test_delivery_adds_stock_and_updates_price(self):
        order = po.create_order(self.vendor, self.kitchen, [(self.tomato, D("10"), None)], self.user)
        line = order.lines.get()
        changes = po.receive_order(order, {line.id: (D("10"), D("3.30"))}, self.user)
        self.assertEqual(st.on_hand(self.kitchen, self.tomato), D("10"))
        self.tomato.refresh_from_db()
        self.assertEqual(self.tomato.last_price, D("3.30"))
        self.assertEqual(len(changes), 1)

    def test_cook_batch_needs_stock(self):
        batch = ProductionBatch.objects.create(location=self.kitchen, item=self.gravy, qty=D("4"), planned_for=date.today())
        with self.assertRaises(ValidationError):
            st.complete_batch(batch, self.user)
        st.record(self.kitchen, self.tomato, "purchase", D("2"), self.user)
        st.record(self.kitchen, self.cream, "purchase", D("1"), self.user)
        st.complete_batch(batch, self.user)
        self.assertEqual(st.on_hand(self.kitchen, self.gravy), D("4"))
        self.assertEqual(st.on_hand(self.kitchen, self.tomato), D("0"))

    def test_transfer_short_receipt(self):
        st.record(self.kitchen, self.gravy, "production_in", D("10"), self.user, unit_cost=D("3.5"))
        t = st.request_transfer(self.kitchen, self.outlet, [(self.gravy, D("6"))], self.user)
        line = t.lines.get()
        with self.assertRaises(ValidationError):
            st.dispatch_transfer(t, {line.id: D("11")}, self.user)
        st.dispatch_transfer(t, {}, self.user)
        short = st.receive_transfer(t, {line.id: D("5.5")}, self.user)
        self.assertEqual(st.on_hand(self.kitchen, self.gravy), D("4"))
        self.assertEqual(st.on_hand(self.outlet, self.gravy), D("5.5"))
        self.assertEqual(len(short), 1)

    def test_variance_report(self):
        day = date(2026, 11, 2)
        st.record(self.outlet, self.gravy, "transfer_in", D("10"), self.user, occurred_on=day, unit_cost=D("3.5"))
        sales.import_day(self.outlet, day, [(self.dish, 20, D("400"))], self.user)  # uses 4 L
        st.log_wastage(self.outlet, self.gravy, D("0.5"), "spoiled", self.user, occurred_on=day)
        st.post_count(self.outlet, [(self.gravy, D("4.5"))], self.user, counted_on=day)  # 1 L unexplained
        r = reports.variance(self.outlet, day, day)
        row = r["items"][0]
        self.assertAlmostEqual(row["theoretical_qty"], 4.0)
        self.assertAlmostEqual(row["wastage_qty"], 0.5)
        self.assertAlmostEqual(row["unexplained_qty"], 1.0)
        self.assertAlmostEqual(r["summary"]["actual_cost"], 5.5 * 3.5)
        self.assertAlmostEqual(r["summary"]["revenue"], 400.0)

    def test_reimporting_sales_replaces_usage(self):
        day = date(2026, 11, 3)
        sales.import_day(self.outlet, day, [(self.dish, 10, D("200"))], self.user)
        sales.import_day(self.outlet, day, [(self.dish, 5, D("100"))], self.user)
        self.assertEqual(st.on_hand(self.outlet, self.gravy), D("-1"))


class PermissionTests(TestCase):
    def setUp(self):
        self.outlet = Location.objects.create(code="O1", name="Outlet", kind="outlet")
        self.other = Location.objects.create(code="O2", name="Other", kind="outlet")
        self.cook = User.objects.create_user("cook", password="x" * 10, role=Role.COOK)
        self.cook.locations.set([self.outlet])
        self.client = APIClient()
        self.client.force_authenticate(self.cook)

    def test_cook_cannot_see_reports(self):
        self.assertEqual(self.client.get("/api/reports/dashboard/").status_code, 403)

    def test_cook_cannot_change_pars(self):
        r = self.client.post("/api/stock/pars/", {"location": self.outlet.id, "pars": []}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_cook_limited_to_own_location(self):
        self.assertEqual(self.client.get(f"/api/stock/levels/?location={self.outlet.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/stock/levels/?location={self.other.id}").status_code, 403)
