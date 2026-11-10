import io
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, User
from catalog.models import Location

from . import services
from .models import ChecklistTemplate, TemplateTask


def jpeg():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (10, 120, 90)).save(buf, "JPEG")
    return SimpleUploadedFile("t.jpg", buf.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT="/tmp/larder-test-media")
class ChecklistTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(code="O1", name="Outlet", kind="outlet")
        self.other = Location.objects.create(code="O2", name="Other", kind="outlet")
        self.cook = User.objects.create_user("cook", password="x" * 10, role=Role.COOK)
        self.cook.locations.set([self.loc])
        self.manager = User.objects.create_user("mgr", password="x" * 10, role=Role.MANAGER)
        self.manager.locations.set([self.loc])
        self.t = ChecklistTemplate.objects.create(name="Closing", kind="closing", applies_to="outlet")
        self.temp = TemplateTask.objects.create(template=self.t, position=0, text="Walk-in temp", value_label="Walk-in",
                                                value_unit="°C", value_min=0, value_max=4, is_critical=True)
        self.door = TemplateTask.objects.create(template=self.t, position=1, text="Doors locked", requires_photo=True)

    def test_cannot_submit_until_complete(self):
        run = services.start_run(self.t, self.loc, date.today(), self.cook)
        with self.assertRaises(ValidationError):
            services.submit_run(run, self.cook)
        temp, door = run.answers.order_by("task__position")
        services.update_answer(temp, self.cook, done=True, value=Decimal("3"))
        services.update_answer(door, self.cook, done=True)
        with self.assertRaises(ValidationError):  # photo still missing
            services.submit_run(run, self.cook)
        services.update_answer(door, self.cook, photo=jpeg())
        self.assertEqual(services.submit_run(run, self.cook), [])
        with self.assertRaises(ValidationError):  # locked after submit
            services.update_answer(temp, self.cook, value=Decimal("2"))

    def test_out_of_range_reading_is_reported(self):
        run = services.start_run(self.t, self.loc, date.today(), self.cook)
        temp, door = run.answers.order_by("task__position")
        services.update_answer(temp, self.cook, done=True, value=Decimal("7"))
        services.update_answer(door, self.cook, done=True, photo=jpeg())
        found = services.submit_run(run, self.cook)
        self.assertEqual(len(found), 1)
        self.assertTrue(any("Out-of-range" in a["title"] for a in services.alerts([self.loc])))

    def test_missing_closing_is_flagged(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        missing = services.compliance([self.loc], yesterday, yesterday)["missing"]
        self.assertEqual(len(missing), 1)

    def test_opening_not_late_before_due_time(self):
        self.t.due_by = time(23, 59)
        self.assertFalse(services.is_late(self.t, timezone.localdate(), now=timezone.localtime().replace(hour=8)))

    def test_api_photo_upload_and_review_permissions(self):
        client = APIClient()
        client.force_authenticate(self.cook)
        r = client.post("/api/checklists/runs/", {"template": self.t.id, "location": self.loc.id}, format="json")
        self.assertEqual(r.status_code, 201)
        run_id = r.data["id"]
        door = next(a for a in r.data["answers"] if a["requires_photo"])
        r = client.patch(f"/api/checklists/runs/{run_id}/answers/{door['id']}/", {"done": "true", "photo": jpeg()}, format="multipart")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["photo_url"].startswith("/media/checklists/"))
        self.assertEqual(client.post(f"/api/checklists/runs/{run_id}/review/", {"decision": "approve"}, format="json").status_code, 403)
        r = client.post("/api/checklists/runs/", {"template": self.t.id, "location": self.other.id}, format="json")
        self.assertEqual(r.status_code, 403)
