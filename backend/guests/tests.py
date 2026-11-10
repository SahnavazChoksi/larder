from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from catalog.models import Location, MenuItem
from ops import labour
from ops.models import Department, Employee, TimeEntry
from pos import services as pos
from pos.models import Order, Payment, Table

from .models import WaitlistEntry


class FrontOfHouseTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="O1", name="Outlet", kind="outlet")
        self.table = Table.objects.create(location=self.loc, name="T1", seats=4)
        self.host = User.objects.create_user("h", password="x" * 10, role=Role.SERVER)
        self.host.locations.set([self.loc])
        self.client = APIClient()
        self.client.force_authenticate(self.host)

    def test_seat_from_waitlist_opens_check_and_records_wait(self):
        w = WaitlistEntry.objects.create(location=self.loc, name="Patel", party_size=3, quoted_minutes=15,
                                         added_at=timezone.now() - timedelta(minutes=20))
        r = self.client.post(f"/api/guests/waitlist/{w.id}/seat/", {"table": self.table.id}, format="json")
        self.assertEqual(r.status_code, 200)
        order = Order.objects.get(pk=r.data["order"])
        self.assertEqual((order.table_id, order.guests), (self.table.id, 3))
        w.refresh_from_db()
        self.assertGreaterEqual(w.waited_minutes, 19)

    def test_clock_in_out_with_pin(self):
        e = Employee.objects.create(location=self.loc, department=Department.SERVICE, name="Ana")
        e.set_pin("4321")
        e.save()
        with self.assertRaises(ValidationError):
            labour.clock(self.loc, "0000")
        emp, direction, _ = labour.clock(self.loc, "4321")
        self.assertEqual((emp, direction), (e, "in"))
        _, direction, entry = labour.clock(self.loc, "4321")
        self.assertEqual(direction, "out")
        self.assertIsNotNone(entry.clock_out)

    def test_tip_pool_split_by_hours(self):
        a = Employee.objects.create(location=self.loc, department=Department.SERVICE, name="A", shares_tips=True)
        b = Employee.objects.create(location=self.loc, department=Department.SERVICE, name="B", shares_tips=True)
        start = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        TimeEntry.objects.create(employee=a, location=self.loc, clock_in=start, clock_out=start + timedelta(hours=6))
        TimeEntry.objects.create(employee=b, location=self.loc, clock_in=start, clock_out=start + timedelta(hours=3))
        dish = MenuItem.objects.create(pos_code="X", name="X", category="Mains", price=Decimal("30"))
        order = pos.open_order(self.loc, self.host, table=self.table, guests=2, at=start)
        pos.add_line(order, dish, 1, self.host)
        pos.send_to_kitchen(order, self.host)
        pos.take_payment(order, self.host, method=Payment.Method.CARD, tip=Decimal("9.00"))
        pool = labour.tip_pool(self.loc, timezone.localdate(start), timezone.localdate(start))
        shares = {s["name"]: s["amount"] for s in pool["shares"]}
        self.assertEqual(shares, {"A": 6.0, "B": 3.0})
