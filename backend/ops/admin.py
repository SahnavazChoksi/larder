from django.contrib import admin

from .models import Complaint, Employee, Equipment, HandoverNote, Issue, Notification, StaffingPlan

admin.site.register(StaffingPlan)
admin.site.register(Equipment)
admin.site.register(HandoverNote)
admin.site.register(Notification)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "department", "position", "is_active")
    list_filter = ("location", "department", "is_active")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("occurred_on", "location", "category", "channel", "detail")
    list_filter = ("location", "category", "channel")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "location", "severity", "status", "created_at")
    list_filter = ("status", "severity", "location")
