from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from catalog.allergens import conflicts, normalise
from catalog.models import Item, Location, MenuItem, MenuLine, Modifier, ModifierGroup
from guests.models import Guest
from sales.models import SalesDay
from stock import services as st

from . import services
from .models import Order, Payment, Table

D = Decimal


class POSTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="O1", name="Outlet", kind="outlet", tax_rate=D("0.13"),
                                           service_charge_rate=D("0.15"), service_charge_party=6, accepts_online_orders=True)
        self.table = Table.objects.create(location=self.loc, name="T1", seats=8)
        self.rice = Item.objects.create(name="Rice", category="Dry", unit="kg", last_price=D("4"))
        self.dish = MenuItem.objects.create(pos_code="R1", name="Rice bowl", category="Mains", price=D("10.00"))
        MenuLine.objects.create(menu_item=self.dish, item=self.rice, qty=D("0.2"))
        self.server = User.objects.create_user("s", password="x" * 10, role=Role.SERVER)
        self.server.locations.set([self.loc])

    def _order(self, guests=2):
        o = services.open_order(self.loc, self.server, table=self.table, guests=guests)
        services.add_line(o, self.dish, 2, self.server)
        return o

    def test_totals_tax_and_service_charge(self):
        o = self._order(guests=2)
        self.assertEqual((o.subtotal, o.service_charge, o.tax, o.total), (D("20.00"), D("0.00"), D("2.60"), D("22.60")))
        services.set_guests(o, 6)
        o.refresh_from_db()
        self.assertEqual(o.service_charge, D("3.00"))          # 15% for 6+
        self.assertEqual(o.tax, D("2.99"))                     # 13% of 23.00
        services.remove_service_charge(o, "Guest asked")
        o.refresh_from_db()
        self.assertEqual(o.total, D("22.60"))

    def test_table_cant_have_two_open_checks(self):
        self._order()
        with self.assertRaises(ValidationError):
            services.open_order(self.loc, self.server, table=self.table, guests=2)

    def test_full_flow_books_sale_stock_prep_and_loyalty(self):
        guest = Guest.objects.create(name="G", is_member=True)
        o = self._order()
        o.guest = guest
        o.save()
        t0 = timezone.now()
        ticket = services.send_to_kitchen(o, self.server, at=t0)
        services.ticket_step(ticket, "start", at=t0 + timedelta(minutes=2))
        services.ticket_step(ticket, "ready", at=t0 + timedelta(minutes=12))
        with self.assertRaises(ValidationError):  # not paid yet
            services.close_order(o, self.server)
        services.take_payment(o, self.server, method=Payment.Method.CARD, tip=D("3.00"))
        services.close_order(Order.objects.get(pk=o.pk), self.server)
        day = SalesDay.objects.get(location=self.loc)
        self.assertEqual((day.covers, day.bills, day.tickets, day.loyalty_bills), (2, 1, 1, 1))
        self.assertEqual(day.prep_minutes, D("12.0"))
        self.assertEqual(st.on_hand(self.loc, self.rice), D("-0.4"))  # 2 portions × 0.2 kg
        guest.refresh_from_db()
        self.assertEqual((guest.points, guest.visits), (20, 1))

    def test_overpay_rejected_and_split(self):
        o = self._order()
        services.send_to_kitchen(o, self.server)
        with self.assertRaises(ValidationError):
            services.take_payment(o, self.server, method=Payment.Method.CASH, amount=D("50"))
        services.take_payment(o, self.server, method=Payment.Method.CASH, amount=D("10.00"), cash_tendered=D("20"))
        services.take_payment(o, self.server, method=Payment.Method.CARD)
        self.assertEqual(Order.objects.get(pk=o.pk).balance(), D("0.00"))

    def test_server_cannot_discount_or_void_sent_items(self):
        o = self._order()
        services.send_to_kitchen(o, self.server)
        client = APIClient()
        client.force_authenticate(self.server)
        self.assertEqual(client.post(f"/api/pos/orders/{o.id}/discount/", {"amount": 5, "reason": "x"}, format="json").status_code, 403)
        line = o.lines.first()
        r = client.post(f"/api/pos/orders/{o.id}/lines/{line.id}/void/", {"reason": "x"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_public_order_goes_to_kitchen(self):
        client = APIClient()
        self.assertEqual(client.get("/api/public/menu/O1/").status_code, 200)
        r = client.post("/api/public/orders/O1/", {"name": "Jo", "phone": "4165550000",
                                                     "lines": [{"menu_item": self.dish.id, "qty": 1}]}, format="json")
        self.assertEqual(r.status_code, 201)
        status = client.get(f"/api/public/order-status/{r.data['token']}/").data
        self.assertEqual(status["state"], "received")

    @override_settings(LARDER_INTEGRATION_SECRET="s3cret")
    def test_delivery_integration_requires_secret(self):
        client = APIClient()
        body = {"location": "O1", "external_ref": "UE-1", "lines": [{"pos_code": "R1", "qty": 1}]}
        self.assertEqual(client.post("/api/pos/integrations/uber_eats/orders/", body, format="json").status_code, 401)
        r = client.post("/api/pos/integrations/uber_eats/orders/", body, format="json", HTTP_X_LARDER_SECRET="s3cret")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Order.objects.get(external_ref="UE-1").status, "closed")


class ModifierTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="O1", name="Outlet", kind="outlet", tax_rate=D("0"))
        self.patty = Item.objects.create(name="Patty", category="Meat", unit="pc", last_price=D("1"))
        self.cheese = Item.objects.create(name="Cheese slice", category="Dairy", unit="pc", last_price=D("0.3"), allergens="Milk")
        self.bun = Item.objects.create(name="Bun", category="Bakery", unit="pc", last_price=D("0.8"), allergens="Gluten, Milk")
        self.burger = MenuItem.objects.create(pos_code="B1", name="Cheeseburger", category="Burgers", price=D("12.00"), contains="Mushroom")
        MenuLine.objects.create(menu_item=self.burger, item=self.bun, qty=1)
        MenuLine.objects.create(menu_item=self.burger, item=self.patty, qty=1)
        self.size = ModifierGroup.objects.create(name="Size", min_choices=1, max_choices=1)
        self.single = Modifier.objects.create(group=self.size, name="Single", is_default=True)
        self.double = Modifier.objects.create(group=self.size, name="Double", price=D("4.50"), item=self.patty, qty=1,
                                              extra_item=self.cheese, extra_qty=1)
        self.extras = ModifierGroup.objects.create(name="Add-ons", max_choices=0)
        self.egg = Modifier.objects.create(group=self.extras, name="Fried egg", price=D("2.50"), allergens="Egg")
        self.burger.modifier_groups.set([self.size, self.extras])
        self.server = User.objects.create_user("s", password="x" * 10, role=Role.SERVER)
        self.server.locations.set([self.loc])
        self.order = services.open_order(self.loc, self.server, type=Order.Type.TAKEOUT)

    def test_required_choice_and_price(self):
        with self.assertRaises(ValidationError):
            services.add_line(self.order, self.burger, 1, self.server)
        line = services.add_line(self.order, self.burger, 2, self.server, modifiers=[self.double.id, self.egg.id])
        self.assertEqual(line.unit_price, D("19.00"))
        self.assertEqual(line.display_name, "Cheeseburger (Double, Fried egg)")
        self.order.refresh_from_db()
        self.assertEqual(self.order.subtotal, D("38.00"))

    def test_two_sizes_rejected_and_defaults_fill(self):
        with self.assertRaises(ValidationError):
            services.add_line(self.order, self.burger, 1, self.server, modifiers=[self.single.id, self.double.id])
        line = services.add_line(self.order, self.burger, 1, None, default_modifiers=True)
        self.assertEqual([m["name"] for m in line.modifiers], ["Single"])

    def test_modifier_stock_is_used_when_sold(self):
        services.add_line(self.order, self.burger, 2, self.server, modifiers=[self.double.id])
        services.send_to_kitchen(self.order, self.server)
        services.take_payment(self.order, self.server, method=Payment.Method.CASH)
        services.close_order(Order.objects.get(pk=self.order.pk), self.server)
        self.assertEqual(st.on_hand(self.loc, self.patty), D("-4"))   # 2 burgers × (1 + 1 extra)
        self.assertEqual(st.on_hand(self.loc, self.cheese), D("-2"))

    def test_allergens_merge_and_match_guests(self):
        self.assertEqual(sorted(self.burger.allergen_set()), ["Gluten", "Milk", "Mushroom"])
        self.assertEqual(conflicts(self.burger.allergen_set(), "lactose intolerant, mushrooms"), ["Milk", "Mushroom"])
        self.assertEqual(conflicts(["Nuts"], "Peanuts"), ["Nuts"])
        self.assertEqual(normalise("shellfish"), {"Shellfish"})
        self.assertEqual(conflicts(self.burger.allergen_set(), ""), [])

    def test_pos_menu_lists_options_and_badges(self):
        client = APIClient()
        client.force_authenticate(self.server)
        data = client.get("/api/pos/menu/").data
        dish = data["items"][0]
        self.assertEqual(dish["allergens"], ["Gluten", "Milk", "Mushroom"])
        self.assertEqual(dish["groups"][0], self.size.id)       # required groups first
        r = client.post(f"/api/pos/orders/{self.order.id}/lines/", {"menu_item": self.burger.id, "modifiers": [self.single.id]},
                        format="json")
        self.assertEqual(r.status_code, 201)
