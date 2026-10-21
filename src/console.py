"""
Ask a running game things.

    python console.py world                  the town in numbers
    python console.py where Maxima           where is she, what does she do
    python console.py npc Maxima             all her stats (also: stats Maxima)
    python console.py follow Maxima          live: prints what she does, phase by phase
    python console.py building "Corner Shop" a building (name or address like 5,5)
    python console.py buildings              all buildings
    python console.py people 20 money        20 citizens, sorted by hunger|money|name
    python console.py graveyard              the dead: cycle of death, name, cause (also: graveyard 50 | all)
    python console.py goods 10               food bought/eaten, money spent, wages
    python console.py map Maxima             town map, * marks where she is
    python console.py                        interactive mode

Names can be shortened to their first letters (as long as they are unique).
The game has to be running (python main.py), see --port.
"""

import argparse
import os
import sys
import time

import protocol
from client import GameClient, GameError, GameConnectionError


# ------------------------------------------------------------ formatting
# (pure functions: data from the game in, text out)

def num(value) -> str:
    if value == float("inf"):
        return "inf"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def fmt_clock(clock:dict) -> str:
    return f"day {clock['day']}, {clock['phase'] or 'before the first phase'}"


def fmt_address(address) -> str:
    return f"{address[0]},{address[1]}" if address else "-"


def fmt_stat(stat:dict) -> str:
    maximum = stat["max"]
    return f"{num(stat['value'])}/{num(maximum)}"


def fmt_where(data:dict) -> str:
    dead = "" if data["alive"] else " (dead)"
    return f"{data['name']}{dead}: {data['action']['text']} at {data['location']['text']} [{fmt_clock(data['clock'])}]"


def fmt_log(entry:dict) -> str:
    return f"day {entry['day']} {entry['phase'] or '-':<18} {entry['text']}"


def fmt_npc(data:dict) -> str:
    location, action = data["location"], data["action"]
    stats, totals = data["stats"], data["totals"]
    home, work, shop = data["home"], data["workplace"], data["shop"]

    lines = [
        f"{data['name']}  [{'alive' if data['alive'] else 'dead'}]",
        f"  where:     {location['text']}  grid {fmt_address(location['address'])}",
        f"  doing:     {action['text']}  [{fmt_clock(data['clock'])}]",
        f"  next:      {data['next']['phase']} -> {data['next']['text']}",
        f"  health {fmt_stat(stats['health'])}   stamina {fmt_stat(stats['stamina'])}   "
        f"hunger {fmt_stat(stats['hunger'])}   money {num(stats['money']['value'])}",
        f"  inventory: food {data['inventory'].get('food', 0)}",
        f"  home:      {home['building'] + ', unit ' + str(home['unit']) if home else '-'}",
        f"  work:      {work['building'] + ' (' + work['role'] + ')' if work else '-'}",
        f"  shop:      {shop['building'] if shop else '-'}",
        f"  routine:   {data['routine']}",
        f"  lifetime:  bought {totals.get('food_bought', 0)} food for {num(totals.get('money_spent', 0))}, "
        f"ate {totals.get('food_eaten', 0)} food, earned {num(totals.get('money_earned', 0))}",
    ]
    if data["log"]:
        lines.append("  recent:")
        lines += [f"    {fmt_log(entry)}" for entry in data["log"]]
    return "\n".join(lines)


def fmt_table(headers:list, rows:list) -> str:
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [max(len(str(h)), *(len(row[i]) for row in rows)) if rows else len(str(h))
              for i, h in enumerate(headers)]
    lines = ["  ".join(str(h).ljust(w) for h, w in zip(headers, widths)).rstrip()]
    lines += ["  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip() for row in rows]
    return "\n".join(lines)


def fmt_people(data:dict) -> str:
    rows = [[p["name"][:8], p["location"], (p["action"] or "-").lower(), p["hunger"],
             num(p["money"]), p["food"], p["workplace"] or "-"] for p in data["people"]]
    table = fmt_table(["name", "location", "action", "hunger", "money", "food", "work"], rows)
    return f"{len(rows)} of {data['total']} citizens, sorted by {data['sort']}\n{table}"


def fmt_buildings(data:dict) -> str:
    rows = []
    for b in data["buildings"]:
        if "residents" in b:
            occupancy = f"{b['residents']}/{b['capacity']} residents"
        elif "employees" in b:
            occupancy = f"{b['employees']}/{b['capacity']} employees"
        else:
            occupancy = "-"
        rows.append([b["name"], b["kind"], fmt_address(b["address"]), b["present"], occupancy])
    return fmt_table(["name", "kind", "grid", "here now", "occupancy"], rows)


def fmt_building(data:dict) -> str:
    lines = [f"{data['name']}  [{data['kind']}, {data['class']}]  grid {fmt_address(data['address'])}",
             f"  here now:   {data['present']}"]
    if data["present_names"]:
        names = ", ".join(name[:8] for name in data["present_names"])
        more = f" ... (+{data['present'] - len(data['present_names'])})" if data["present"] > len(data["present_names"]) else ""
        lines.append(f"              {names}{more}")

    kind = data["kind"]
    if kind == "home":
        lines += [f"  units:      {data['units']}",
                  f"  residents:  {data['residents']}/{data['capacity']}",
                  f"  rent:       {data['rent']} per day, quality {data['quality']}",
                  f"  effect:     health {data['gain']['health']}, stamina {data['gain']['stamina']}, "
                  f"hunger {data['gain']['hunger']} per day"]
    elif kind in ("work", "shop"):
        lines += [f"  employees:  {data['employees']}/{data['capacity']}",
                  f"  working now: {data['working_now']}",
                  f"  boss:       {data['boss'] or '-'}"]
        if kind == "shop":
            lines += [f"  food price: {data['food_price']}",
                      f"  sold:       {data['sold']} food, revenue {data['revenue']}"]
    elif kind == "tile":
        lines.append(f"  owner:      {data['owner'] or '-'}")
    else:
        lines.append(f"  citizens:   {data['citizens']}, buildings: {data['buildings']}")
    return "\n".join(lines)


def fmt_graveyard(data:dict) -> str:
    if not data["total"]:
        return "the graveyard is empty"

    head = f"graveyard: {data['total']} buried"
    if data["shown"] < data["total"]:
        head += f", showing the {data['shown']} most recent ('graveyard N' or 'graveyard all' for more)"
    rows = [[grave["cycle"], grave["name"], grave["cause"]] for grave in data["graves"]]
    return head + "\n" + fmt_table(["cycle", "name", "cause"], rows)


def fmt_ledger_line(label:str, counts:dict) -> str:
    return (f"  {label:<10} food bought {counts.get('food_bought', 0)}, eaten {counts.get('food_eaten', 0)}, "
            f"money spent {counts.get('money_spent', 0)}, wages paid {counts.get('wages_paid', 0)}")


def fmt_world(data:dict) -> str:
    pop = data["population"]
    census = ", ".join(f"{place} {count}" for place, count in sorted(data["census"].items(), key=lambda i: -i[1]))
    kinds = ", ".join(f"{count} {kind}" for kind, count in sorted(data["buildings"].items()))
    last = data["last_cycle"]
    lines = [
        f"{data['town']}  -  {fmt_clock(data['clock'])}",
        f"  population: {pop['alive']} alive, {pop['deaths']} died so far",
        f"  last cycle: {last['cycle']} ({last['died']} died, {last['new']} new)" if last["cycle"] else
        "  last cycle: none finished yet",
        f"  where:      {census or '-'}",
        f"  buildings:  {kinds or '-'}",
        f"  food stock: {data['totals']['food']} items in inventories",
        fmt_ledger_line("today:", data["today"]),
        fmt_ledger_line("total:", data["total"]),
    ]
    if data["recent_deaths"]:
        deaths = ", ".join(f"{d['name'][:8]} (cycle {d['cycle']})" for d in data["recent_deaths"])
        lines.append(f"  last deaths: {deaths}")
    return "\n".join(lines)


def fmt_goods(data:dict) -> str:
    lines = [f"goods and money  -  day {data['day']} running, {data['food_stock']} food in inventories",
             fmt_ledger_line("today:", data["today"]), fmt_ledger_line("total:", data["total"])]
    for shop in data["shops"]:
        lines.append(f"  {shop['name']}: sold {shop['sold']} food at {shop['price']} each, revenue {shop['revenue']}")
    if data["history"]:
        rows = [[h["day"], h["food_bought"], h["food_eaten"], h["money_spent"], h["wages_paid"],
                 h.get("food_stock", "-"), h.get("alive", "-")] for h in data["history"]]
        lines += ["", fmt_table(["day", "bought", "eaten", "spent", "wages", "stock", "alive"], rows)]
    else:
        lines.append("  (no finished day yet)")
    return "\n".join(lines)


def fmt_map(data:dict, mark=None, mark_name:str="") -> str:
    bounds = data["bounds"]
    if not bounds:
        return "(nothing built yet)"
    if bounds["max_x"] - bounds["min_x"] > 40:
        return "the town is too wide for the text map, use display.py"

    cells = {tuple(c["pos"]): c for c in data["cells"]}
    mark = tuple(mark) if mark else None
    lines = []
    for y in range(bounds["max_y"], bounds["min_y"] - 1, -1):
        row = []
        for x in range(bounds["min_x"], bounds["max_x"] + 1):
            cell = cells.get((y, x))
            symbol = cell["symbol"][:2] if cell else ".."
            row.append(symbol.ljust(2) + ("*" if (y, x) == mark else " "))
        lines.append(f"{y:>4} " + "".join(row).rstrip())
    header = "     " + "".join(f"{x:<3}" if x % 5 == 0 else "   " for x in range(bounds["min_x"], bounds["max_x"] + 1))
    legend = "TH town hall, MB mega building, MN mansion, SH shop, WB workplace, other = tile"
    if mark:
        legend += f", * = {mark_name}"
    return "\n".join([header.rstrip()] + lines + ["", legend])


# ------------------------------------------------------------ commands

def need(args:list, what:str) -> str:
    if not args:
        raise GameError(f"missing argument: {what}")
    return " ".join(args)


def cmd_world(client, args, out):
    out(fmt_world(client.request("world")))


def cmd_where(client, args, out):
    out(fmt_where(client.request("where", need(args, "npc name"))))


def cmd_npc(client, args, out):
    out(fmt_npc(client.request("npc", need(args, "npc name"))))


def cmd_people(client, args, out):
    out(fmt_people(client.request("people", *args[:2])))


def cmd_graveyard(client, args, out):
    out(fmt_graveyard(client.request("graveyard", *args[:1])))


def cmd_buildings(client, args, out):
    out(fmt_buildings(client.request("buildings")))


def cmd_building(client, args, out):
    out(fmt_building(client.request("building", need(args, "building name or address"))))


def cmd_goods(client, args, out):
    out(fmt_goods(client.request("goods", *args[:1])))


def cmd_map(client, args, out):
    mark, name = None, ""
    if args:
        where = client.request("where", " ".join(args))
        mark, name = where["location"]["address"], where["name"]
    out(fmt_map(client.request("map"), mark, name))


def follow(client, name:str, out=print, interval:float=0.25, max_updates=None, sleep=time.sleep) -> None:
    """
    Prints a line whenever the npc is in a new phase or place or does something
    new, plus everything that happens to it (buying, eating, earning).
    Runs until Ctrl+C, the npc is gone or `max_updates` lines were printed.
    """
    out(f"following {name} - Ctrl+C to stop")
    out("(start main.py with --delay 0.5 to see every single phase)")

    last_state, seen, printed = None, set(), 0
    while max_updates is None or printed < max_updates:
        try:
            data = client.request("npc", name)
        except GameError as error:
            out(f"stopped: {error}")
            return

        state = (data["clock"]["day"], data["clock"]["phase"], data["location"]["text"], data["action"]["type"])
        if state != last_state:
            last_state = state
            stats = data["stats"]
            out(f"day {data['clock']['day']:<3} {data['clock']['phase'] or '-':<19} {data['action']['text']} "
                f"at {data['location']['text']}  | money {num(stats['money']['value'])} "
                f"hunger {stats['hunger']['value']} food {data['inventory'].get('food', 0)}")
            printed += 1

        for entry in data["log"]:
            key = (entry["day"], entry["phase"], entry["text"])
            if key not in seen:
                seen.add(key)
                out(f"        * {fmt_log(entry)}")

        sleep(interval)


def cmd_follow(client, args, out):
    follow(client, need(args, "npc name"), out)


COMMANDS = {
    "world": (cmd_world, "the town in numbers"),
    "where": (cmd_where, "<npc>  where is the npc and what does it do"),
    "npc": (cmd_npc, "<npc>  all stats of an npc"),
    "follow": (cmd_follow, "<npc>  live view of what the npc does"),
    "building": (cmd_building, "<name|y,x>  details of a building"),
    "buildings": (cmd_buildings, "all buildings"),
    "people": (cmd_people, "[N] [hunger|money|name]  list citizens"),
    "graveyard": (cmd_graveyard, "[N|all]  the dead: cycle of death, name, cause (newest first)"),
    "goods": (cmd_goods, "[days]  food bought/eaten, money spent, wages"),
    "map": (cmd_map, "[npc]  town map, marks where the npc is"),
}

ALIASES = {"location": "where", "loc": "where", "stats": "npc", "status": "world", "town": "world",
           "npcs": "people", "ledger": "goods", "graves": "graveyard", "dead": "graveyard"}


def help_text() -> str:
    lines = ["commands:"] + [f"  {name:<10} {text}" for name, (_, text) in COMMANDS.items()]
    lines += ["  help       this text", "  quit       leave (interactive mode)",
              "names can be shortened to their first letters, e.g. 'where max'"]
    return "\n".join(lines)


def execute(client, words:list, out=print) -> None:
    """runs one command line, raises GameError / GameConnectionError"""
    name = words[0].lower().rstrip(":")     # also accept 'location:'
    name = ALIASES.get(name, name)
    if name == "help":
        out(help_text())
        return
    if name not in COMMANDS:
        raise GameError(f"unknown command {words[0]!r}, type 'help'")
    COMMANDS[name][0](client, words[1:], out)


def interactive(client) -> None:
    print("connected. type 'help' for commands, 'quit' to leave.")
    while True:
        try:
            line = input("game> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            return
        try:
            execute(client, line.split())
        except GameError as error:
            print(f"error: {error}")
        except GameConnectionError as error:
            print(f"error: {error}")
        except KeyboardInterrupt:
            print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ask a running TownSim game things. Without a command: interactive mode.",
                                     epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="see below, e.g.  where Maxima")
    args = parser.parse_args(argv)

    client = GameClient(args.host, args.port)
    try:
        if args.command:
            execute(client, args.command)
        else:
            client.connect()
            interactive(client)
    except GameError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except GameConnectionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print()
    except BrokenPipeError:
        # output was cut off, e.g. `console.py follow max | head`: leave quietly
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
