from decimal import Decimal

from django.conf import settings
from django.db import models

from catalog.models import Location

User = settings.AUTH_USER_MODEL


class SOP(models.Model):
    """A standard operating procedure: how a task is done here. Linked from checklist tasks."""

    title = models.CharField(max_length=120)
    category = models.CharField(max_length=40, help_text="e.g. Food safety, Cleaning, Cash")
    body = models.TextField(help_text="One step per line")
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]
        verbose_name = "SOP"

    def __str__(self):
        return self.title

    @property
    def steps(self):
        return [line.strip() for line in self.body.splitlines() if line.strip()]


class ChecklistTemplate(models.Model):
    class Kind(models.TextChoices):
        OPENING = "opening", "Opening"
        CLOSING = "closing", "Closing"
        SHIFT = "shift", "During shift"

    class AppliesTo(models.TextChoices):
        OUTLET = "outlet", "Outlets"
        KITCHEN = "kitchen", "Central kitchen"
        ALL = "all", "Every location"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    applies_to = models.CharField(max_length=8, choices=AppliesTo.choices, default=AppliesTo.OUTLET)
    due_by = models.TimeField(null=True, blank=True, help_text="Should be submitted by this time (local)")
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return self.name

    def applies(self, location: Location) -> bool:
        return self.applies_to in (self.AppliesTo.ALL, location.kind)


class TemplateTask(models.Model):
    """One line on a checklist. Removed tasks are deactivated, not deleted, so history stays readable."""

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="tasks")
    position = models.PositiveSmallIntegerField(default=0)
    text = models.CharField(max_length=200)
    sop = models.ForeignKey(SOP, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    requires_photo = models.BooleanField(default=False)
    value_label = models.CharField(max_length=60, blank=True, help_text="Ask for a reading, e.g. 'Walk-in temperature'")
    value_unit = models.CharField(max_length=12, blank=True, help_text="e.g. °C, $")
    value_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    value_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_critical = models.BooleanField(default=False, help_text="Food safety or security: alert managers if it fails")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text

    def in_range(self, value: Decimal | None) -> bool:
        if value is None:
            return True
        if self.value_min is not None and value < self.value_min:
            return False
        if self.value_max is not None and value > self.value_max:
            return False
        return True


class ChecklistRun(models.Model):
    """One checklist done at one location on one business day."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Waiting for review"
        APPROVED = "approved", "Approved"
        FLAGGED = "flagged", "Flagged"

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name="runs")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="checklist_runs")
    business_date = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    started_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-business_date", "template__kind"]
        unique_together = [("template", "location", "business_date")]

    @property
    def number(self):
        return f"CL-{self.id}"


def photo_path(answer, filename):
    ext = (filename.rsplit(".", 1)[-1] or "jpg").lower()[:5]
    run = answer.run
    return f"checklists/{run.business_date:%Y/%m}/{run.location.code}-{run.id}-{answer.task_id}.{ext}"


class RunAnswer(models.Model):
    run = models.ForeignKey(ChecklistRun, on_delete=models.CASCADE, related_name="answers")
    task = models.ForeignKey(TemplateTask, on_delete=models.PROTECT, related_name="answers")
    task_text = models.CharField(max_length=200, help_text="Copy of the task wording at the time")
    done = models.BooleanField(default=False)
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    photo = models.ImageField(upload_to=photo_path, blank=True)
    done_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["task__position", "task_id"]
        unique_together = [("run", "task")]

    @property
    def out_of_range(self) -> bool:
        return not self.task.in_range(self.value)
