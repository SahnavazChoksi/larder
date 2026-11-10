from django.contrib import admin

from .models import Guest, Message, PointsEntry, Reservation, WaitlistEntry


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_member", "points", "visits", "total_spent", "last_visit")
    search_fields = ("name", "phone", "email")
    list_filter = ("is_member",)


admin.site.register(PointsEntry)
admin.site.register(Reservation)
admin.site.register(WaitlistEntry)
admin.site.register(Message)
