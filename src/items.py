"""
Items: what an item is, which items exist (the catalog) and how a file with
new items is checked. The file format is described in the README.

Checking is strict on purpose: a typo like "pirce" must never be ignored
silently, so unknown fields, wrong types and unknown categories are errors.
`parse_document` collects ALL problems of a file, each with its place in the
file like  items[0].price: must be a whole number >= 0, got "3".
"""

import difflib
import json
import re
from dataclasses import dataclass


FORMAT_VERSION = 1

ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,39}")
NAME_MAX = 60

EFFECT_KEYS = ("health", "stamina", "hunger")

COMMON_FIELDS = ("id", "name", "category", "price", "stock", "description", "store", "deliver_to")
# what a category adds to the common fields (more categories will come)
CATEGORY_FIELDS = {"food": ("effects",)}
CATEGORIES = tuple(CATEGORY_FIELDS)


@dataclass(frozen=True)
class ItemDef:
    """what an item is. The same everywhere in the town, whoever sells or owns it."""
    id: str
    name: str
    category: str
    effects: dict           # what one piece does to the sim that uses it
    description: str = ""


# the food every shop sells from the start (unless it is started without)
BUILTIN_FOOD = ItemDef("food", "food", "food", {"hunger": -1}, "plain food")
BUILTIN = {BUILTIN_FOOD.id: BUILTIN_FOOD}


class Catalog:
    """all items the town knows"""

    def __init__(self):
        self.items = dict(BUILTIN)

    def get(self, item_id:str):
        return self.items.get(item_id)

    def add(self, item:ItemDef) -> None:
        self.items[item.id] = item

    def __contains__(self, item_id:str) -> bool:
        return item_id in self.items

    def __iter__(self):
        return iter(self.items.values())

    def __len__(self) -> int:
        return len(self.items)


@dataclass
class ItemSpec:
    """one item of a checked file"""
    id: str
    name: str
    category: str
    price: int
    stock: int
    effects: dict
    description: str = ""
    store: str = None           # name of the shop, None: the first shop
    deliver_to: str = None      # name of a sim who gets the pieces directly

    def definition(self) -> ItemDef:
        return ItemDef(self.id, self.name, self.category, dict(self.effects), self.description)

    def target(self):
        """where the pieces go, used to find items that are listed twice"""
        if self.deliver_to:
            return ("sim", self.deliver_to.lower())
        return ("shop", self.store.lower() if self.store else None)


class _DuplicateKey(Exception):
    pass


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def whole(value) -> bool:
    """a whole number (True and 3.0 are not)"""
    return type(value) is int


def show(value) -> str:
    text = json.dumps(value)
    return text if len(text) <= 40 else text[:37] + "..."


def unknown_name(what:str, path:str, key:str, allowed) -> str:
    """message for a field or effect that does not exist, with a hint for typos"""
    close = difflib.get_close_matches(key, allowed, n=1)
    hint = f'did you mean "{close[0]}"?' if close else f"allowed: {', '.join(allowed)}"
    return f"{path}: unknown {what} ({hint})"


def parse_document(text:str):
    """
    Checks the text of a file. Returns (specs, errors). If there is any error,
    specs is empty: a file is taken over completely or not at all.
    """
    try:
        document = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except _DuplicateKey as error:
        return [], [f'(file): the key "{error.args[0]}" appears twice in the same object']
    except json.JSONDecodeError as error:
        return [], [f"(file): not valid JSON: {error.msg} (line {error.lineno}, column {error.colno})"]

    specs, errors = check_document(document)
    return ([], errors) if errors else (specs, [])


def check_document(document):
    if not isinstance(document, dict):
        return [], ['(file): must be a JSON object like {"format": 1, "items": [...]}']

    errors = []
    for key in document:
        if key not in ("format", "items"):
            errors.append(unknown_name("field", key, key, ("format", "items")))

    if "format" not in document:
        errors.append(f"format: is required (use {FORMAT_VERSION})")
    elif not whole(document["format"]) or document["format"] != FORMAT_VERSION:
        errors.append(f"format: must be {FORMAT_VERSION}, got {show(document['format'])}")

    raw_items = document.get("items")
    if "items" not in document:
        errors.append("items: is required")
        return [], errors
    if not isinstance(raw_items, list):
        errors.append("items: must be a list")
        return [], errors
    if not raw_items:
        errors.append("items: must contain at least one item")
        return [], errors

    specs = []
    for index, raw in enumerate(raw_items):
        spec, problems = check_item(raw, f"items[{index}]")
        errors += problems
        specs.append(spec)

    # the same item twice for the same target is most likely a mistake
    first = {}
    for index, spec in enumerate(specs):
        if spec is None:
            continue
        key = (spec.id, spec.target())
        if key in first:
            errors.append(f'items[{index}].id: "{spec.id}" is listed twice for the same target '
                          f'(first at items[{first[key]}])')
        else:
            first[key] = index

    return [spec for spec in specs if spec is not None], errors


def check_item(raw, path:str):
    """returns (ItemSpec or None, errors)"""
    if not isinstance(raw, dict):
        return None, [f"{path}: must be an object"]

    errors = []
    category = raw.get("category")
    category_ok = isinstance(category, str) and category in CATEGORIES

    if category_ok:
        allowed = COMMON_FIELDS + CATEGORY_FIELDS[category]
    else:       # do not complain about fields of categories that might be the intended one
        allowed = COMMON_FIELDS + tuple(sorted({f for fields in CATEGORY_FIELDS.values() for f in fields}))
    for key in raw:
        if key not in allowed:
            errors.append(unknown_name("field", f"{path}.{key}", key, allowed))

    def required(key, check):
        if key not in raw:
            errors.append(f"{path}.{key}: is required")
            return None
        problem = check(raw[key])
        if problem:
            errors.append(f"{path}.{key}: {problem}")
            return None
        return raw[key]

    def optional(key, check):
        if key not in raw:
            return None
        problem = check(raw[key])
        if problem:
            errors.append(f"{path}.{key}: {problem}")
            return None
        return raw[key]

    def check_id(value):
        if not (isinstance(value, str) and ID_PATTERN.fullmatch(value)):
            return ("must start with a lowercase letter and then have only lowercase letters, digits, "
                    f"_ or - (at most 40 characters), got {show(value)}")

    def check_name(value):
        if not (isinstance(value, str) and 1 <= len(value.strip()) and len(value) <= NAME_MAX):
            return f"must be text with 1 to {NAME_MAX} characters, got {show(value)}"

    def check_category(value):
        if not (isinstance(value, str) and value in CATEGORIES):
            return f"must be one of: {', '.join(CATEGORIES)}, got {show(value)}"

    def check_amount(value):
        if not whole(value) or value < 0:
            return f"must be a whole number >= 0, got {show(value)}"

    def check_text(value):
        if not isinstance(value, str):
            return f"must be text, got {show(value)}"

    def check_name_of_target(value):
        if not (isinstance(value, str) and value.strip()):
            return f"must be a name (text), got {show(value)}"

    item_id = required("id", check_id)
    name = required("name", check_name)
    required("category", check_category)
    price = required("price", check_amount)
    stock = required("stock", check_amount)
    description = optional("description", check_text)
    store = optional("store", check_name_of_target)
    deliver_to = optional("deliver_to", check_name_of_target)
    if "store" in raw and "deliver_to" in raw:
        errors.append(f'{path}: use either "store" or "deliver_to", not both')

    effects = {}
    if category_ok and category == "food":
        effects = check_food_effects(raw, path, errors)

    if errors:
        return None, errors

    return ItemSpec(id=item_id, name=name.strip(), category=category, price=price, stock=stock,
                    effects=effects, description=description or "",
                    store=store.strip() if store else None,
                    deliver_to=deliver_to.strip() if deliver_to else None), []


def check_food_effects(raw, path:str, errors:list) -> dict:
    if "effects" not in raw:
        errors.append(f"{path}.effects: is required for food")
        return {}

    effects = raw["effects"]
    if not isinstance(effects, dict):
        errors.append(f'{path}.effects: must be an object like {{"hunger": -2}}, got {show(effects)}')
        return {}

    problems = len(errors)
    for key, value in effects.items():
        if key not in EFFECT_KEYS:
            errors.append(unknown_name("effect", f"{path}.effects.{key}", key, EFFECT_KEYS))
        elif not whole(value):
            errors.append(f"{path}.effects.{key}: must be a whole number, got {show(value)}")
    if len(errors) > problems:
        return {}

    if "hunger" not in effects:
        errors.append(f'{path}.effects: a food has to lower hunger, add "hunger" with a negative number like -2')
        return {}
    if effects["hunger"] >= 0:
        errors.append(f"{path}.effects.hunger: a food has to lower hunger, use a negative number "
                      f"like -2 (got {effects['hunger']})")
        return {}

    return {key: value for key, value in effects.items() if value != 0}
