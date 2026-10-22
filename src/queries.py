"""
Everything a client can ask the running game.

All functions only READ the simulation and return plain data (dicts, lists,
numbers, strings) that can be sent as JSON. `run()` is the single entry point,
it takes the simulation lock so the answer always shows a consistent state.
"""

import re

from buildings import Unit, HomeBuilding, WorkBuilding, Shop, Tile
from person import ActionType
from simulation import location_label


class QueryError(Exception):
    """the question cannot be answered, the message is shown to the user"""


ACTION_TEXT = {
    ActionType.WAKEUP: "waking up",
    ActionType.GO_TO_WORK: "on the way to work",
    ActionType.WORK: "working",
    ActionType.GO_TO_SHOP: "on the way to the shop",
    ActionType.SHOP: "shopping",
    ActionType.GO_TO_LEISURE: "on the way to leisure",
    ActionType.LEISURE: "relaxing",
    ActionType.GO_HOME: "going home",
    ActionType.SLEEP: "sleeping",
}


# children do not work and do not shop
CHILD_STAYS_HOME = (ActionType.GO_TO_WORK, ActionType.WORK, ActionType.GO_TO_SHOP, ActionType.SHOP)


# ---------------------------------------------------------------- helpers

def building_kind(building) -> str:
    if isinstance(building, Shop):
        return "shop"
    if isinstance(building, WorkBuilding):
        return "work"
    if isinstance(building, HomeBuilding):
        return "home"
    if isinstance(building, Tile):
        return "tile"
    return "townhall"       # the only other thing that sits on the grid


def building_name(building) -> str:
    return getattr(building, "name", None) or getattr(building, "town_name", None) or str(building)


def address_of(building):
    address = getattr(building, "address", None)
    return list(address) if isinstance(address, tuple) else None


def people_in(building) -> list:
    """everybody who is in the building right now"""
    if isinstance(building, HomeBuilding):
        return [person for unit in building.units.values() for person in unit.currently_here]
    return list(getattr(building, "currently_here", []))


def short(name) -> str:
    return str(name)[:8]


def find_person(sim, query:str):
    typed = query.strip()
    query = typed.lower()
    if not query:
        raise QueryError("which npc? give a name (or the first letters of it)")

    citizens = sim.town_hall.citizens
    exact = [p for p in citizens if str(p.name).lower() == query]
    if len(exact) == 1:
        return exact[0]

    matches = exact or [p for p in citizens if str(p.name).lower().startswith(query)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(short(p.name) for p in matches[:5])
        more = f" and {len(matches) - 5} more" if len(matches) > 5 else ""
        raise QueryError(f"{len(matches)} npcs match {typed!r}: {names}{more}. Type more letters.")

    grave = sim.town_hall.graveyard.find(query)
    if grave:
        raise QueryError(f"{grave.name} died in cycle {grave.cycle} ({grave.cause})")
    raise QueryError(f"no npc named {typed!r}")


def find_building(sim, query:str):
    typed = query.strip()
    query = typed.lower()
    if not query:
        raise QueryError("which building? give a name or an address like 5,5")

    town_hall = sim.town_hall
    grid = town_hall.town_grid.grid

    pos = re.fullmatch(r"\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?", query)
    if pos:
        found = grid.get((int(pos.group(1)), int(pos.group(2))))
        if found is None:
            raise QueryError(f"nothing is built at {typed}")
        return found

    everything = [town_hall] + list(town_hall.buildings)
    exact = [b for b in everything if building_name(b).lower() == query]
    if len(exact) == 1:
        return exact[0]

    matches = exact or [b for b in everything if query in building_name(b).lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise QueryError(f"no building named {typed!r}")

    options = ", ".join(f"{building_name(b)} {address_of(b)}" for b in matches[:5])
    raise QueryError(f"{len(matches)} buildings match {typed!r}: {options}. Use the address, e.g. 5,5")


def shop_stock(shop, catalog) -> list:
    """what a shop has for sale"""
    stock = []
    for offer in shop.stock.values():
        item = catalog.get(offer.item_id)
        stock.append({"item": offer.item_id, "name": item.name if item else offer.item_id,
                      "price": offer.price, "quantity": offer.quantity})
    return stock


def location_info(person) -> dict:
    location = person.current_location
    if location is None:
        return {"kind": "nowhere", "building": None, "unit": None, "address": None, "text": "nowhere"}

    if isinstance(location, Unit):
        building = location.building
        return {
            "kind": "home",
            "building": building.name,
            "unit": location.unit_number,
            "address": address_of(building),
            "text": f"{building.name} (home, unit {location.unit_number})",
        }

    kind = building_kind(location)
    name = building_name(location)
    return {"kind": kind, "building": name, "unit": None, "address": address_of(location),
            "text": f"{name} ({kind})"}


def action_info(person) -> dict:
    action = person.current_action
    if action is None:
        return {"type": None, "text": "has not done anything yet", "phase": None}

    text = ACTION_TEXT[action]
    wanted = {
        ActionType.GO_TO_WORK: ("a workplace", person.workplace),
        ActionType.WORK: ("a workplace", person.workplace),
        ActionType.GO_TO_SHOP: ("a shop", person.shop),
        ActionType.SHOP: ("a shop", person.shop),
        ActionType.GO_TO_LEISURE: ("a leisure place", person.leisure_spot),
        ActionType.LEISURE: ("a leisure place", person.leisure_spot),
    }.get(action)
    if wanted and wanted[1] is None:
        if not person.is_adult and action in CHILD_STAYS_HOME:
            text += " (too young, stays home)"
        else:
            text += f" (has no {wanted[0].split(' ', 1)[1]}, stays home)"

    return {"type": action.name, "text": text,
            "phase": person.last_phase.name if person.last_phase else None}


def stat(current, maximum) -> dict:
    return {"value": current, "max": maximum}


# ---------------------------------------------------------------- commands

def cmd_ping(sim, args):
    return {"pong": True, "town": sim.town_hall.town_name}


def person_info(sim, person) -> dict:
    attributes = person.attributes
    next_phase = sim.phase
    next_action = person.routine[next_phase]

    home = person.home
    workplace = person.workplace
    return {
        "name": str(person.name),
        "alive": person.alive,
        "clock": sim.clock(),
        "location": location_info(person),
        "action": action_info(person),
        "next": {"phase": next_phase.name, "action": next_action.name, "text": ACTION_TEXT[next_action]},
        "stats": {
            "health": stat(attributes.health, attributes.max_health),
            "stamina": stat(attributes.stamina, attributes.max_stamina),
            "hunger": stat(attributes.hunger, attributes.max_hunger),
            "money": stat(attributes.money, attributes.max_money),
            "age": stat(person.age, person.lifespan),
        },
        "inventory": dict(person.inventory),
        "home": None if home is None else {"building": home.building.name, "unit": home.unit_number,
                                          "address": address_of(home.building)},
        "workplace": None if workplace is None else {"building": workplace.name,
                                                    "role": workplace.roles.get(person, "worker"),
                                                    "address": address_of(workplace)},
        "shop": None if person.shop is None else {"building": person.shop.name, "address": address_of(person.shop)},
        "routine": person.routine_id,
        "adult": person.is_adult,
        "parents": None if person.parents is None else list(person.parents),
        "children": person.children,
        "pregnancy": None if person.pregnancy is None else {
            "due_cycle": person.pregnancy.due_cycle, "partner": str(person.pregnancy.partner.name)},
        "totals": dict(person.totals),
        "log": [{"day": day, "phase": phase, "text": text} for day, phase, text in person.log],
    }


def cmd_npc(sim, args):
    return person_info(sim, find_person(sim, " ".join(args)))


def cmd_where(sim, args):
    person = find_person(sim, " ".join(args))
    return {
        "name": str(person.name),
        "alive": person.alive,
        "clock": sim.clock(),
        "location": location_info(person),
        "action": action_info(person),
    }


def cmd_world(sim, args):
    town_hall = sim.town_hall
    ledger = town_hall.ledger

    kinds = {}
    for building in town_hall.buildings:
        kind = building_kind(building)
        kinds[kind] = kinds.get(kind, 0) + 1

    living = sim.living()
    return {
        "town": town_hall.town_name,
        "clock": sim.clock(),
        "population": {"alive": len(living), "deaths": sim.deaths,
                       "children": sum(1 for p in living if not p.is_adult),
                       "pregnant": sum(1 for p in living if p.pregnancy is not None)},
        "last_cycle": sim.last_cycle(),
        "census": dict(sim.census()),
        "today": dict(ledger.today),
        "total": dict(ledger.total),
        "buildings": kinds,
        "totals": sim.totals(),
        "recent_deaths": [grave._asdict() for grave in town_hall.graveyard.latest(5)],
    }


MAX_GRAVES = 5000       # keeps one answer well below the size limit of the protocol


def cmd_graveyard(sim, args):
    graveyard = sim.town_hall.graveyard
    total = len(graveyard)

    wanted = args[0].lower() if args else "20"
    if wanted == "all":
        limit = MAX_GRAVES
    else:
        try:
            limit = int(wanted)
        except ValueError:
            raise QueryError(f"{args[0]!r} is not a number, use a number or 'all'")
        if limit < 1:
            raise QueryError("the number must be 1 or more")
        limit = min(limit, MAX_GRAVES)

    graves = graveyard.latest(limit)
    return {"total": total, "shown": len(graves), "graves": [grave._asdict() for grave in graves]}


def cmd_people(sim, args):
    try:
        limit = int(args[0]) if args else 15
    except ValueError:
        raise QueryError(f"{args[0]!r} is not a number")
    sort = args[1] if len(args) > 1 else "hunger"
    limit = max(1, min(limit, 200))

    sorters = {
        "hunger": lambda p: -p.attributes.hunger,
        "money": lambda p: -p.money() if p.money() != float("inf") else float("-inf"),
        "name": lambda p: str(p.name),
        "age": lambda p: -p.age,
    }
    if sort not in sorters:
        raise QueryError(f"cannot sort by {sort!r}, use one of: {', '.join(sorters)}")

    living = sorted(sim.living(), key=sorters[sort])
    return {
        "total": len(living),
        "sort": sort,
        "people": [
            {
                "name": str(p.name),
                "location": location_info(p)["text"],
                "action": p.current_action.name if p.current_action else None,
                "age": p.age,
                "hunger": p.attributes.hunger,
                "money": p.money(),
                "food": p.inventory["food"],
                "workplace": p.workplace.name if p.workplace else None,
            }
            for p in living[:limit]
        ],
    }


def building_summary(building) -> dict:
    kind = building_kind(building)
    info = {"name": building_name(building), "kind": kind, "address": address_of(building),
            "present": len(people_in(building))}
    if kind == "home":
        info["residents"], info["capacity"] = building.residents(), building.max_residents
    elif kind in ("work", "shop"):
        info["employees"], info["capacity"] = len(building.employees), building.work_places
    return info


def cmd_buildings(sim, args):
    town_hall = sim.town_hall
    entries = [{"name": town_hall.town_name, "kind": "townhall", "address": list(town_hall.address),
                "present": 0}]
    entries += [building_summary(b) for b in town_hall.buildings]
    return {"buildings": entries}


def cmd_building(sim, args):
    building = find_building(sim, " ".join(args))
    kind = building_kind(building)
    here = people_in(building)

    info = {"name": building_name(building), "kind": kind, "class": type(building).__name__,
            "address": address_of(building) or list(getattr(building, "address", []) or []),
            "present": len(here), "present_names": [str(p.name) for p in here[:15]]}

    if kind == "home":
        info.update({
            "units": len(building.units),
            "residents": building.residents(),
            "capacity": building.max_residents,
            "quality": building.quality(),
            "rent": building.rent(),
            "gain": {"health": building.gain_stats.health, "stamina": building.gain_stats.stamina,
                     "hunger": building.gain_stats.hunger},
        })
    elif kind in ("work", "shop"):
        working = [p for p in here if p.current_action == ActionType.WORK and p.workplace is building]
        info.update({
            "employees": len(building.employees),
            "capacity": building.work_places,
            "boss": None if building.boss is None else str(building.boss.name),
            "working_now": len(working),
        })
        if kind == "shop":
            info.update({"food_price": building.food_price, "sold": building.sold, "revenue": building.revenue,
                         "stock": shop_stock(building, sim.town_hall.catalog)})
    elif kind == "tile":
        info["owner"] = None if building.owner is None else str(building.owner.name)
    else:
        info.update({"citizens": len(sim.town_hall.citizens), "buildings": len(sim.town_hall.buildings)})

    return info


def cmd_goods(sim, args):
    try:
        days = int(args[0]) if args else 10
    except ValueError:
        raise QueryError(f"{args[0]!r} is not a number")
    days = max(1, min(days, 100))

    town_hall = sim.town_hall
    ledger = town_hall.ledger
    return {
        "day": ledger.day,
        "today": dict(ledger.today),
        "total": dict(ledger.total),
        "history": list(ledger.history)[-days:],
        "food_stock": sim.totals()["food"],
        "shops": [{"name": s.name, "price": s.food_price, "sold": s.sold, "revenue": s.revenue,
                   "items": shop_stock(s, town_hall.catalog)} for s in town_hall.shop_buildings],
    }


def cmd_items(sim, args):
    """every item the town knows: what it does, where it is sold, how many pieces sims hold"""
    town_hall = sim.town_hall
    held = {}
    for citizen in sim.living():
        for item_id, count in citizen.inventory.items():
            if count > 0:
                held[item_id] = held.get(item_id, 0) + count

    entries = []
    for item in town_hall.catalog:
        offers = []
        for shop in town_hall.shop_buildings:
            offer = shop.stock.get(item.id)
            if offer is not None:
                offers.append({"shop": shop.name, "price": offer.price, "quantity": offer.quantity})
        entries.append({"id": item.id, "name": item.name, "category": item.category,
                        "effects": dict(item.effects), "description": item.description,
                        "offers": offers, "held": held.get(item.id, 0)})
    return {"items": entries}


def cmd_map(sim, args):
    town_hall = sim.town_hall
    cells = []
    for (y, x), thing in town_hall.town_grid.grid.items():
        kind = building_kind(thing)
        cells.append({
            "pos": [y, x],
            "kind": kind,
            "name": building_name(thing),
            "symbol": str(thing),
            "present": len(people_in(thing)),
        })
    if not cells:
        return {"cells": [], "bounds": None}

    ys = [c["pos"][0] for c in cells]
    xs = [c["pos"][1] for c in cells]
    return {"cells": cells, "bounds": {"min_y": min(ys), "max_y": max(ys), "min_x": min(xs), "max_x": max(xs)}}


def cmd_snapshot(sim, args):
    """world, goods, map, buildings and (optionally) one npc, all taken at the same moment"""
    snapshot = {
        "world": cmd_world(sim, []),
        "goods": cmd_goods(sim, ["30"]),
        "map": cmd_map(sim, []),
        "buildings": cmd_buildings(sim, []),
        "watch": None,
        "watch_error": None,
    }
    name = " ".join(args).strip()
    if name:
        try:
            snapshot["watch"] = person_info(sim, find_person(sim, name))
        except QueryError as error:
            snapshot["watch_error"] = str(error)
    return snapshot


COMMANDS = {
    "ping": cmd_ping,
    "world": cmd_world,
    "npc": cmd_npc,
    "where": cmd_where,
    "people": cmd_people,
    "graveyard": cmd_graveyard,
    "buildings": cmd_buildings,
    "building": cmd_building,
    "goods": cmd_goods,
    "items": cmd_items,
    "map": cmd_map,
    "snapshot": cmd_snapshot,
}


def run(sim, cmd:str, args:list):
    """answers one question, raises QueryError if it cannot be answered"""
    handler = COMMANDS.get(cmd)
    if handler is None:
        raise QueryError(f"unknown command {cmd!r}, known: {', '.join(COMMANDS)}")

    with sim.lock:
        return handler(sim, [str(arg) for arg in args])
