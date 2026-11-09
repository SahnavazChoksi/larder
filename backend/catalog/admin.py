from django.contrib import admin

from .models import Item, Location, MenuItem, MenuLine, PriceHistory, RecipeLine, Vendor


class RecipeLineInline(admin.TabularInline):
    model = RecipeLine
    fk_name = "prep"
    extra = 0


class MenuLineInline(admin.TabularInline):
    model = MenuLine
    extra = 0


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "kind", "city")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "lead_days", "delivery_days")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "kind", "unit", "last_price", "vendor", "is_active")
    list_filter = ("kind", "category", "vendor")
    search_fields = ("name",)
    inlines = [RecipeLineInline]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "pos_code", "category", "price", "is_active")
    inlines = [MenuLineInline]


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("item", "price", "vendor", "recorded_on", "source")
    list_filter = ("vendor",)
