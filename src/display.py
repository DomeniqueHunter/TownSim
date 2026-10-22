"""
A window that shows the running game: the town map, who is where, goods bought
and eaten, all buildings and one npc you watch (Maxima by default).

    python display.py                     watch Maxima
    python display.py --watch Minimus     watch somebody else (or type a name in the window)
    python display.py --port 7799         if the game runs on another port

The game has to be running (python main.py). To see every phase of the day
start it slower:  python main.py --delay 0.5

Needs tkinter (comes with Python on Windows and macOS,
on Debian/Ubuntu: sudo apt install python3-tk).
"""

import argparse
import sys

import console
import protocol
from client import GameClient, GameError, GameConnectionError


REFRESH_MS = 500

MAP_SIZE = (470, 470)
CHART_SIZE = (470, 190)

KIND_COLORS = {
    "home": "#9ecae1",
    "work": "#fdae6b",
    "shop": "#a1d99b",
    "tile": "#e5e5e5",
    "townhall": "#bcbddc",
}
WATCH_COLOR = "#d62728"
CHART_SERIES = (("food_bought", "#2ca02c", "bought"), ("food_eaten", "#d62728", "eaten"))


# ------------------------------------------------------------------ pure parts
# Everything below until DisplayApp has no tkinter in it and can be tested.

def cell_rect(bounds:dict, pos, width:int, height:int, margin:int=22) -> tuple:
    """pixel rectangle (x0, y0, x1, y1) of the map cell at grid position pos=(y, x), north is up"""
    columns = bounds["max_x"] - bounds["min_x"] + 1
    rows = bounds["max_y"] - bounds["min_y"] + 1
    size = min((width - 2 * margin) / columns, (height - 2 * margin) / rows)

    y, x = pos
    x0 = margin + (x - bounds["min_x"]) * size
    y0 = margin + (bounds["max_y"] - y) * size
    return (x0, y0, x0 + size, y0 + size)


def draw_map(canvas, map_data:dict, width:int, height:int, watch_address=None) -> None:
    """draws the town, the building the watched npc is in gets a red frame"""
    canvas.delete("all")
    bounds = map_data["bounds"]
    if not bounds:
        canvas.create_text(width / 2, height / 2, text="nothing built yet")
        return

    watch = tuple(watch_address) if watch_address else None
    for cell in map_data["cells"]:
        x0, y0, x1, y1 = cell_rect(bounds, cell["pos"], width, height)
        size = x1 - x0
        watched = watch == tuple(cell["pos"])

        canvas.create_rectangle(x0, y0, x1, y1, fill=KIND_COLORS.get(cell["kind"], "#ffffff"),
                                outline=WATCH_COLOR if watched else "#888888", width=3 if watched else 1)
        if size >= 14:
            canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2 - (5 if cell["present"] and size >= 26 else 0),
                               text=cell["symbol"])
        if cell["present"] and size >= 26:
            canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 8, text=str(cell["present"]), fill="#333333")
        if watched:
            canvas.create_oval(x1 - 9, y0 + 1, x1 - 1, y0 + 9, fill=WATCH_COLOR, outline="")


def draw_chart(canvas, history:list, width:int, height:int, margin:int=34) -> None:
    """food bought and eaten per day"""
    canvas.delete("all")
    if len(history) < 2:
        canvas.create_text(width / 2, height / 2, text="food per day: waiting for two finished days")
        return

    top = max(1, max(entry[key] for entry in history for key, _, _ in CHART_SERIES))
    first, last = history[0]["day"], history[-1]["day"]
    plot_w, plot_h = width - 2 * margin, height - 2 * margin

    def point(index:int, value:int) -> tuple:
        return (margin + plot_w * index / (len(history) - 1), margin + plot_h * (1 - value / top))

    canvas.create_line(margin, margin, margin, height - margin, fill="#888888")
    canvas.create_line(margin, height - margin, width - margin, height - margin, fill="#888888")
    canvas.create_text(margin - 4, margin, text=str(top), anchor="e")
    canvas.create_text(margin - 4, height - margin, text="0", anchor="e")
    canvas.create_text(margin, height - margin + 12, text=f"day {first}", anchor="w")
    canvas.create_text(width - margin, height - margin + 12, text=f"day {last}", anchor="e")

    for number, (key, color, label) in enumerate(CHART_SERIES):
        points = [coordinate for index, entry in enumerate(history) for coordinate in point(index, entry[key])]
        canvas.create_line(*points, fill=color, width=2)
        canvas.create_text(margin + 70 * number + 6, 12, text=label, fill=color, anchor="w")


def goods_text(goods:dict) -> str:
    lines = [f"day {goods['day']} running, {goods['food_stock']} food in inventories",
             console.fmt_ledger_line("today:", goods["today"]),
             console.fmt_ledger_line("total:", goods["total"])]
    for shop in goods["shops"]:
        lines.append(f"  {shop['name']}: sold {shop['sold']}, revenue {shop['revenue']}; "
                     f"for sale: {console.fmt_offers(shop['items'])}")
    if goods["history"]:
        last = goods["history"][-1]
        lines.append(f"  last day ({last['day']}): bought {last['food_bought']}, eaten {last['food_eaten']}, "
                     f"stock {last.get('food_stock', '-')}")
    return "\n".join(lines)


def header_text(snapshot:dict) -> str:
    world = snapshot["world"]
    pop = world["population"]
    return (f"{world['town']}   |   {console.fmt_clock(world['clock'])}   |   "
            f"{pop['alive']} alive, {pop['deaths']} dead")


def watch_text(snapshot:dict) -> str:
    if snapshot["watch"] is not None:
        return console.fmt_npc(snapshot["watch"])
    return snapshot["watch_error"] or "type a name below to follow an npc"


def building_rows(snapshot:dict) -> list:
    rows = []
    for b in snapshot["buildings"]["buildings"]:
        if "residents" in b:
            occupancy = f"{b['residents']}/{b['capacity']}"
        elif "employees" in b:
            occupancy = f"{b['employees']}/{b['capacity']}"
        else:
            occupancy = "-"
        rows.append((b["name"], b["kind"], console.fmt_address(b["address"]), b["present"], occupancy))
    return rows


# ------------------------------------------------------------------ the window

class DisplayApp:
    """
    The window. `tk` and `ttk` are the tkinter modules, handed in so the
    window code can be tried out without a screen.
    """

    def __init__(self, tk, ttk, root, client, watch:str="", interval_ms:int=REFRESH_MS):
        self.tk, self.root, self.client = tk, root, client
        self.watch, self.interval_ms = watch, interval_ms

        root.title("TownSim")

        self.header = ttk.Label(root, text="connecting ...", font=("TkDefaultFont", 12, "bold"))
        self.header.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        self.map_canvas = tk.Canvas(root, width=MAP_SIZE[0], height=MAP_SIZE[1], background="white")
        self.map_canvas.grid(row=1, column=0, padx=8, pady=4)

        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="n", padx=8, pady=4)
        self.watch_entry = ttk.Entry(right, width=30)
        self.watch_entry.insert(0, watch)
        self.watch_entry.grid(row=0, column=0, sticky="w")
        self.watch_entry.bind("<Return>", lambda event: self.set_watch())
        ttk.Button(right, text="Watch", command=self.set_watch).grid(row=0, column=1, padx=4)
        self.watch_box = self.make_text(right, height=24, width=78)
        self.watch_box.grid(row=1, column=0, columnspan=2, pady=4)

        self.chart_canvas = tk.Canvas(root, width=CHART_SIZE[0], height=CHART_SIZE[1], background="white")
        self.chart_canvas.grid(row=2, column=0, padx=8, pady=4)

        self.world_box = self.make_text(root, height=12, width=78)
        self.world_box.grid(row=2, column=1, padx=8, pady=4, sticky="n")

        columns = ("name", "kind", "grid", "here", "occupancy")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=7)
        for column in columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=130 if column == "name" else 90)
        self.tree.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=4)

        self.status = ttk.Label(root, text="")
        self.status.grid(row=4, column=0, columnspan=2, sticky="w", padx=8)

    def make_text(self, parent, height:int, width:int):
        box = self.tk.Text(parent, height=height, width=width, font="TkFixedFont", wrap="none")
        box.configure(state="disabled")
        return box

    def set_text(self, box, text:str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def set_watch(self) -> None:
        self.watch = self.watch_entry.get().strip()
        self.refresh(reschedule=False)

    def render(self, snapshot:dict) -> None:
        self.header.configure(text=header_text(snapshot))

        watched = snapshot["watch"]
        address = watched["location"]["address"] if watched else None
        draw_map(self.map_canvas, snapshot["map"], MAP_SIZE[0], MAP_SIZE[1], address)
        draw_chart(self.chart_canvas, snapshot["goods"]["history"], CHART_SIZE[0], CHART_SIZE[1])

        self.set_text(self.watch_box, watch_text(snapshot))
        self.set_text(self.world_box, console.fmt_world(snapshot["world"]) + "\n\n" + goods_text(snapshot["goods"]))

        self.tree.delete(*self.tree.get_children())
        for row in building_rows(snapshot):
            self.tree.insert("", "end", values=row)

    def refresh(self, reschedule:bool=True) -> None:
        try:
            self.render(self.client.request("snapshot", self.watch))
            self.status.configure(text=f"connected to {self.client.host}:{self.client.port}")
        except (GameConnectionError, GameError) as error:
            self.status.configure(text=str(error))     # keep showing the last picture, try again

        if reschedule:
            self.root.after(self.interval_ms, self.refresh)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Window showing a running TownSim game.")
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--watch", default="Maxima", help="npc to watch (default: Maxima)")
    parser.add_argument("--interval", type=int, default=REFRESH_MS, metavar="MS",
                        help=f"how often the window updates (default: {REFRESH_MS})")
    args = parser.parse_args(argv)

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        print("error: tkinter is not installed (Debian/Ubuntu: sudo apt install python3-tk). "
              "console.py works without it.", file=sys.stderr)
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"error: cannot open a window ({error})", file=sys.stderr)
        return 1

    client = GameClient(args.host, args.port, timeout=2.0)
    app = DisplayApp(tk, ttk, root, client, args.watch, args.interval)
    app.refresh()
    try:
        root.mainloop()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
