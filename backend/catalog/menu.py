"""The menu as order-takers see it: tiles, badges, allergens, options and suggestions. No costs."""
from django.db.models import Prefetch

from .allergens import vocabulary
from .models import Item, MenuCategory, MenuItem, Modifier, ModifierGroup


def _photo(request, dish):
    if not dish.photo:
        return None
    return request.build_absolute_uri(dish.photo.url) if request else dish.photo.url


def _split(text):
    return {a.strip() for a in text.split(",") if a.strip()}


def _item_allergens(item, depth=0):
    """Like Item.allergen_set, but reads prefetched recipe lines instead of querying per dish."""
    found = _split(item.allergens)
    if item.kind == Item.Kind.PREP and depth <= 6:
        for rl in item.recipe_lines.all():
            found |= _item_allergens(rl.component, depth + 1)
    return found


def _dish_allergens(dish):
    found = _split(dish.contains)
    for line in dish.lines.all():
        found |= _item_allergens(line.item)
    return found


def menu_payload(request=None, public=False) -> dict:
    dishes = list(
        MenuItem.objects.filter(is_active=True)
        .prefetch_related("lines__item__recipe_lines__component", "pairs_with",
                          Prefetch("modifier_groups", queryset=ModifierGroup.objects.prefetch_related(
                              Prefetch("options", queryset=Modifier.objects.filter(is_active=True).select_related("item", "extra_item")
                              .prefetch_related("item__recipe_lines__component", "extra_item__recipe_lines__component")))))
        .order_by("category", "sort_order", "name")
    )
    cats = {c.name: c for c in MenuCategory.objects.all()}
    used = {d.category for d in dishes}
    categories = [{"name": c.name, "icon": c.icon, "kind": c.kind} for c in cats.values() if c.name in used]
    categories += [{"name": n, "icon": "", "kind": "main"} for n in sorted(used - set(cats))]
    order = {c["name"]: i for i, c in enumerate(categories)}
    dishes.sort(key=lambda d: (order[d.category], d.sort_order, d.name))

    groups = {}
    for d in dishes:
        for g in d.modifier_groups.all():
            if g.id not in groups:
                groups[g.id] = {
                    "id": g.id, "name": g.label if public and g.label else g.name, "min": g.min_choices, "max": g.max_choices, "sort": g.sort_order,
                    "options": [{"id": m.id, "name": m.name, "price": float(m.price), "is_veg": m.is_veg, "is_default": m.is_default,
                                 "allergens": sorted(_split(m.allergens).union(*(_item_allergens(i) for i, _ in m.usage())))}
                                for m in g.options.all()],
                }
    live = {d.id for d in dishes}
    items = []
    for d in dishes:
        items.append({
            "id": d.id, "pos_code": d.pos_code, "name": d.name, "category": d.category, "price": float(d.price),
            "icon": d.icon or cats.get(d.category, MenuCategory(icon="")).icon, "photo": _photo(request, d),
            "description": d.description, "diet": d.diet, "spice": d.spice_level, "chef_pick": d.is_chef_pick, "new": d.is_new,
            "allergens": sorted(_dish_allergens(d)), "note": d.dietary_note,
            "ingredients": [] if public else [line.item.name for line in d.lines.all() if line.item.category != "Packaging"],
            "groups": sorted((g.id for g in d.modifier_groups.all()), key=lambda gid: (groups[gid]["min"] == 0, groups[gid]["sort"], gid)),
            "pairs": [p.id for p in d.pairs_with.all() if p.id in live],
        })
    return {"categories": categories, "items": items, "groups": groups, "allergens": vocabulary()}
