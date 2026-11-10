from django.contrib import admin

from .models import SOP, ChecklistRun, ChecklistTemplate, RunAnswer, TemplateTask


class TaskInline(admin.TabularInline):
    model = TemplateTask
    extra = 0


class AnswerInline(admin.TabularInline):
    model = RunAnswer
    extra = 0
    readonly_fields = ("task_text", "done", "value", "note", "photo", "done_by", "done_at")
    can_delete = False


@admin.register(ChecklistTemplate)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "applies_to", "due_by", "is_active")
    inlines = [TaskInline]


@admin.register(ChecklistRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ("business_date", "template", "location", "status", "submitted_by", "reviewed_by")
    list_filter = ("status", "location", "template")
    inlines = [AnswerInline]


@admin.register(SOP)
class SOPAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "updated_at")
    list_filter = ("category",)
