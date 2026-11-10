from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from catalog.models import Item, Location, MenuItem, Vendor
from purchasing import invoices
from reports.performance import performance
from sales.services import import_day

from . import services
from .models import Department, Employee, Notification, StaffingPlan


class StaffingAndNotifyTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="O1", name="Outlet", kind="outlet", brand="B")
        self.mgr = User.objects.create_user("m", password="x" * 10, role=Role.MANAGER, email="m@example.com")
        self.mgr.locations.set([self.loc])

    def test_staffing_gap(self):
        StaffingPlan.objects.create(location=self.loc, department=Department.SERVICE, required=5)
        for i in range(3):
            Employee.objects.create(location=self.loc, department=Department.SERVICE, name=f"E{i}")
        Employee.objects.create(location=self.loc, department=Department.SERVICE, name="Gone", is_active=False)
        s = services.staffing([self.loc])
        self.assertEqual(s["total"], {"required": 5, "actual": 3, "gap": 2})

    def test_notify_is_idempotent_per_key(self):
        users = services.managers_for(self.loc)
        self.assertEqual(services.notify(users, "Hi", key="k1"), 1)
        self.assertEqual(services.notify(users, "Hi", key="k1"), 0)
        self.assertEqual(Notification.objects.count(), 1)


class PerformanceTests(TestCase):
    def setUp(self):
        self.a = Location.objects.create(code="A", name="A", kind="outlet", brand="B")
        self.b = Location.objects.create(code="B", name="B", kind="outlet", brand="B")
        self.owner = User.objects.create_user("o", password="x" * 10, role=Role.OWNER)
        self.main = MenuItem.objects.create(pos_code="M", name="Main", category="Mains", price=Decimal("20"))
        self.drink = MenuItem.objects.create(pos_code="D", name="Drink", category="Drinks", price=Decimal("5"))
        self.end = date(2026, 11, 8)
        for loc, now, before in ((self.a, 120, 100), (self.b, 90, 100)):
            for back in range(28):
                d = self.end - timedelta(days=back)
                import_day(loc, d, [(self.main, now, Decimal(20 * now)), (self.drink, 30, Decimal(150))], self.owner,
                           totals={"covers": 100, "bills": 40, "sc_bills": 10, "sc_removed": 1}, history=True)
                import_day(loc, d - timedelta(days=364), [(self.main, before, Decimal(20 * before))], self.owner,
                           totals={"covers": 100, "bills": 40}, history=True)

    def test_apc_sssg_attach(self):
        r = performance(self.owner, self.end)
        a = next(x for x in r["outlets"] if x["code"] == "A")
        self.assertAlmostEqual(a["apc"], (2400 + 150) / 100)
        self.assertAlmostEqual(a["sssg_4w"], 2550 / 2000 - 1)
        self.assertAlmostEqual(a["bev_attach"], 0.3)
        self.assertAlmostEqual(a["sc_removed_pct"], 0.1)
        brand = r["brand_avg"]["B"]
        self.assertAlmostEqual(brand["sssg_4w"], (2550 + 1950) / 4000 - 1)


@override_settings(MEDIA_ROOT="/tmp/larder-test-media", ANTHROPIC_API_KEY="test-key")
class InvoiceTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="CK", name="Kitchen", kind="kitchen")
        self.vendor = Vendor.objects.create(name="Peel Fresh Meats", lead_days=1)
        self.chicken = Item.objects.create(name="Chicken thigh, boneless", category="Meat", unit="kg",
                                           vendor=self.vendor, last_price=Decimal("16"))
        self.mgr = User.objects.create_user("m", password="x" * 10, role=Role.MANAGER)
        self.mgr.locations.set([self.loc])

    def test_scan_matches_and_approves(self):
        fake = {"vendor_name": "PEEL FRESH MEATS INC", "invoice_number": "INV-1", "invoice_date": "2026-11-08",
                "lines": [{"description": "CHKN THIGH BONELESS", "quantity": 22.0462, "unit": "lb", "unit_price": 7.9}]}
        with mock.patch.object(invoices, "_call_claude", return_value=fake):
            upload = SimpleUploadedFile("inv.jpg", b"\xff\xd8\xff fake", content_type="image/jpeg")
            scan = invoices.create_scan(self.loc, upload, self.mgr)
        self.assertEqual(scan.vendor, self.vendor)
        line = scan.lines[0]
        self.assertEqual(line["item"], self.chicken.id)
        self.assertAlmostEqual(line["qty"], 10.0, places=2)  # 22.05 lb → 10 kg
        order = invoices.approve(scan, self.mgr)
        self.assertEqual(order.status, "received")
        self.chicken.refresh_from_db()
        self.assertAlmostEqual(float(self.chicken.last_price), 17.42, places=1)

    def test_rejects_other_files(self):
        with self.assertRaises(ValidationError):
            invoices.create_scan(self.loc, SimpleUploadedFile("x.txt", b"hi", content_type="text/plain"), self.mgr)

    def test_cook_cannot_approve(self):
        cook = User.objects.create_user("c", password="x" * 10, role=Role.COOK)
        cook.locations.set([self.loc])
        client = APIClient()
        client.force_authenticate(cook)
        self.assertEqual(client.post("/api/purchasing/invoices/1/approve/").status_code, 403)
