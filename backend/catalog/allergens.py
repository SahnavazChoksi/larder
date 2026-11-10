"""One vocabulary for allergens, so a guest's "dairy" matches a dish that carries "Milk".

Dishes and ingredients store allergens as free text (comma separated). Guests' allergies are free text too
("peanuts, shellfish", "no dairy"). Both are mapped onto the names below before they are compared.
"""
import re

# Canonical name → words that mean it
ALLERGENS = {
    "Milk": ["milk", "dairy", "lactose"],
    "Egg": ["egg", "eggs"],
    "Gluten": ["gluten", "wheat", "celiac", "coeliac"],
    "Peanut": ["peanut", "peanuts", "groundnut"],
    "Nuts": ["nut", "nuts", "tree nut", "tree nuts", "walnut", "pecan", "almond", "cashew", "pistachio", "hazelnut"],
    "Soy": ["soy", "soya"],
    "Sesame": ["sesame"],
    "Mustard": ["mustard"],
    "Mushroom": ["mushroom", "mushrooms", "fungi", "truffle"],
    "Fish": ["fish", "anchovy"],
    "Shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
    "Alcohol": ["alcohol", "rum", "wine", "beer"],
}
ICONS = {"Milk": "🥛", "Egg": "🥚", "Gluten": "🌾", "Peanut": "🥜", "Nuts": "🌰", "Soy": "🫘", "Sesame": "◌",
         "Mustard": "🟡", "Mushroom": "🍄", "Fish": "🐟", "Shellfish": "🦐", "Alcohol": "🍷"}
_WORDS = sorted(((w, name) for name, words in ALLERGENS.items() for w in [name.lower(), *words]), key=lambda x: -len(x[0]))


def normalise(text: str) -> set[str]:
    """Free text → canonical allergen names. Unknown words are ignored."""
    found, rest = set(), f" {text.lower()} "
    for word, name in _WORDS:
        pattern = rf"(?<![a-z]){re.escape(word)}(?![a-z])"
        if re.search(pattern, rest):
            found.add(name)
            rest = re.sub(pattern, " ", rest)
    return found


def vocabulary() -> list[dict]:
    """For the POS and online menu: names, icons and the words that match them."""
    return [{"name": n, "icon": ICONS.get(n, ""), "words": [n.lower(), *w]} for n, w in ALLERGENS.items()]


def conflicts(dish_allergens, guest_allergies: str) -> list[str]:
    """Allergens on the dish that the guest has told us about. Peanut allergies also flag tree nuts (shared kitchens)."""
    guest = normalise(guest_allergies or "")
    if not guest:
        return []
    dish = set()
    for a in dish_allergens:
        dish |= normalise(a) or {a}
    hits = guest & dish
    if "Peanut" in guest and "Nuts" in dish:
        hits.add("Nuts")
    return sorted(hits)
