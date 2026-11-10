from django.contrib import admin

from .models import (
    Item, Location, MenuCategory, MenuItem, MenuLine, Modifier, ModifierGroup, PriceHistory, RecipeLine, Vendor,
)


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
    list_display = ("name", "pos_code", "category", "price", "diet", "spice_level", "is_chef_pick", "is_new", "is_active")
    list_filter = ("category", "diet", "is_chef_pick", "is_new", "is_active")
    search_fields = ("name", "pos_code")
    filter_horizontal = ("pairs_with", "modifier_groups")
    inlines = [MenuLineInline]


@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "kind", "sort_order")
    list_editable = ("icon", "kind", "sort_order")


class ModifierInline(admin.TabularInline):
    model = Modifier
    fk_name = "group"
    extra = 0


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "min_choices", "max_choices", "sort_order")
    inlines = [ModifierInline]


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("item", "price", "vendor", "recorded_on", "source")
    list_filter = ("vendor",)
