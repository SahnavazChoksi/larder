from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class LarderUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Larder access", {"fields": ("role", "locations")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Larder access", {"fields": ("role", "locations")}),)
    list_display = ("username", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active")
    filter_horizontal = ("groups", "user_permissions", "locations")
