
import unittest
from unittest import mock

import display
import queries
from client import GameClient, GameConnectionError
from display import (cell_rect, draw_map, draw_chart, goods_text, header_text, watch_text, building_rows,
                     DisplayApp, KIND_COLORS, WATCH_COLOR, MAP_SIZE, CHART_SIZE)
from gameserver import GameServer

from townhelper import make_sim


class FakeCanvas:
    """remembers what was drawn"""

    def __init__(self):
        self.calls = []

    def delete(self, *args):
        self.calls = []

    def __getattr__(self, name):
        if not name.startswith("create_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))

    def of(self, kind):
        return [(args, kwargs) for name, args, kwargs in self.calls if name == f"create_{kind}"]

    def texts(self):
        return [kwargs.get("text") for _, kwargs in self.of("text")]


def snapshot_of(sim, watch="Maxima"):
    return queries.run(sim, "snapshot", [watch])


class TestMapDrawing(unittest.TestCase):

    BOUNDS = {"min_y": -2, "max_y": 2, "min_x": -2, "max_x": 2}

    def test_cell_rect_north_is_up_east_is_right(self):
        top_left = cell_rect(self.BOUNDS, (2, -2), 100, 100, margin=0)
        bottom_right = cell_rect(self.BOUNDS, (-2, 2), 100, 100, margin=0)

        self.assertEqual((0, 0, 20, 20), top_left)
        self.assertEqual((80, 80, 100, 100), bottom_right)

    def test_cells_do_not_overlap_and_stay_inside_the_margin(self):
        rects = [cell_rect(self.BOUNDS, (y, x), 200, 100, margin=10) for y in range(-2, 3) for x in range(-2, 3)]

        self.assertEqual(25, len(set(rects)))
        self.assertTrue(all(10 <= x0 and x1 <= 190 and 10 <= y0 and y1 <= 90 for x0, y0, x1, y1 in rects))
        # cells are square
        self.assertTrue(all(abs((x1 - x0) - (y1 - y0)) < 1e-9 for x0, y0, x1, y1 in rects))

    def test_one_rectangle_per_cell_in_the_color_of_its_kind(self):
        sim = make_sim()
        sim.step()
        canvas = FakeCanvas()
        data = queries.run(sim, "map", [])

        draw_map(canvas, data, *MAP_SIZE)

        rectangles = canvas.of("rectangle")
        self.assertEqual(len(data["cells"]), len(rectangles))
        fills = {kwargs["fill"] for _, kwargs in rectangles}
        self.assertEqual({KIND_COLORS["home"], KIND_COLORS["work"], KIND_COLORS["shop"],
                          KIND_COLORS["tile"], KIND_COLORS["townhall"]}, fills)
        self.assertIn("MN", canvas.texts())
        self.assertIn("TH", canvas.texts())

    def test_the_watched_building_is_marked(self):
        sim = make_sim()
        for _ in range(7):
            sim.step()          # EVENING: Maxima is relaxing at home in the Villa
        snapshot = snapshot_of(sim, "Maxima")
        canvas = FakeCanvas()

        draw_map(canvas, snapshot["map"], *MAP_SIZE, watch_address=snapshot["watch"]["location"]["address"])

        marked = [(args, kwargs) for args, kwargs in canvas.of("rectangle") if kwargs["outline"] == WATCH_COLOR]
        self.assertEqual(1, len(marked))
        villa = cell_rect(snapshot["map"]["bounds"], (5, 5), *MAP_SIZE)
        self.assertEqual(villa, tuple(marked[0][0]))
        self.assertEqual(1, len(canvas.of("oval")))

    def test_nobody_watched_nothing_marked(self):
        sim = make_sim()
        sim.step()
        canvas = FakeCanvas()
        draw_map(canvas, queries.run(sim, "map", []), *MAP_SIZE)

        self.assertFalse([1 for _, kwargs in canvas.of("rectangle") if kwargs["outline"] == WATCH_COLOR])
        self.assertEqual([], canvas.of("oval"))

    def test_empty_town(self):
        canvas = FakeCanvas()
        draw_map(canvas, {"cells": [], "bounds": None}, *MAP_SIZE)
        self.assertEqual(["nothing built yet"], canvas.texts())

    def test_drawing_again_starts_with_an_empty_canvas(self):
        sim = make_sim()
        sim.step()
        canvas = FakeCanvas()
        data = queries.run(sim, "map", [])
        draw_map(canvas, data, *MAP_SIZE)
        draw_map(canvas, data, *MAP_SIZE)
        self.assertEqual(len(data["cells"]), len(canvas.of("rectangle")))


class TestChartDrawing(unittest.TestCase):

    HISTORY = [{"day": d, "food_bought": 10 * d, "food_eaten": 5 * d} for d in range(1, 6)]

    def test_needs_two_days(self):
        canvas = FakeCanvas()
        draw_chart(canvas, self.HISTORY[:1], *CHART_SIZE)
        self.assertIn("waiting", canvas.texts()[0])
        self.assertEqual([], canvas.of("line"))

    def test_two_lines_and_labels(self):
        canvas = FakeCanvas()
        draw_chart(canvas, self.HISTORY, *CHART_SIZE)

        series = [(args, kwargs) for args, kwargs in canvas.of("line") if kwargs.get("width") == 2]
        self.assertEqual(2, len(series))
        for args, _ in series:
            self.assertEqual(10, len(args))                      # 5 days -> 5 points
        self.assertTrue({"bought", "eaten", "day 1", "day 5", "50"} <= set(canvas.texts()))

    def test_higher_values_are_drawn_higher(self):
        canvas = FakeCanvas()
        draw_chart(canvas, self.HISTORY, *CHART_SIZE)
        bought, eaten = [args for args, kwargs in canvas.of("line") if kwargs.get("width") == 2]

        ys_bought, ys_eaten = bought[1::2], eaten[1::2]
        self.assertTrue(all(b < e for b, e in zip(ys_bought, ys_eaten)))     # smaller y = higher up
        self.assertEqual(sorted(ys_bought, reverse=True), list(ys_bought))   # rising

    def test_flat_zero_history_does_not_divide_by_zero(self):
        canvas = FakeCanvas()
        draw_chart(canvas, [{"day": 1, "food_bought": 0, "food_eaten": 0},
                            {"day": 2, "food_bought": 0, "food_eaten": 0}], *CHART_SIZE)
        self.assertEqual(2, len([1 for _, kw in canvas.of("line") if kw.get("width") == 2]))


class TestTexts(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)
        for _ in range(3):
            self.sim.step()
        self.snapshot = snapshot_of(self.sim)

    def test_header(self):
        self.assertEqual("Testville   |   day 3, NOON   |   5 alive, 0 dead", header_text(self.snapshot))

    def test_goods_text(self):
        text = goods_text(self.snapshot["goods"])
        self.assertIn("day 3 running", text)
        self.assertIn("Shop: sold", text)
        self.assertIn("last day (2)", text)

    def test_goods_text_without_a_finished_day(self):
        sim = make_sim()
        sim.step()
        text = goods_text(snapshot_of(sim)["goods"])
        self.assertNotIn("last day", text)

    def test_watch_text(self):
        self.assertIn("Maxima  [alive]", watch_text(self.snapshot))
        self.assertIn("no npc named 'Zed'", watch_text(snapshot_of(self.sim, "Zed")))
        self.assertIn("type a name", watch_text(snapshot_of(self.sim, "")))

    def test_building_rows(self):
        rows = building_rows(self.snapshot)
        self.assertEqual(7, len(rows))
        self.assertIn(("Villa", "home", "5,5", 1, "1/2"), rows)
        job = next(row for row in rows if row[0] == "Job")
        self.assertEqual(("Job", "work"), job[:2])
        self.assertEqual("3/3", job[4])
        self.assertRegex(job[2], r"^-?\d+,-?\d+$")


class TestWindowLogic(unittest.TestCase):
    """
    The window itself, run with a pretend tkinter (there may be no screen).
    This finds mistakes in our own code, not in the way tkinter is used.
    """

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)
        self.server = GameServer(self.sim, port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.client = GameClient(port=self.server.port, timeout=2)
        self.addCleanup(self.client.close)

        self.tk, self.ttk, self.root = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
        # like the real thing: every widget is a new object
        for module, names in ((self.tk, ("Canvas", "Text")),
                              (self.ttk, ("Label", "Frame", "Entry", "Button", "Treeview"))):
            for name in names:
                getattr(module, name).side_effect = lambda *args, **kwargs: mock.MagicMock()
        self.app = DisplayApp(self.tk, self.ttk, self.root, self.client, watch="Maxima", interval_ms=250)

    def texts_written(self, box):
        return [call.args[1] for call in box.insert.call_args_list]

    def test_builds_all_widgets(self):
        self.root.title.assert_called_with("TownSim")
        self.assertEqual(2, self.tk.Canvas.call_count)
        self.assertEqual(2, self.tk.Text.call_count)
        self.ttk.Treeview.assert_called_once()
        self.assertIsNot(self.app.watch_box, self.app.world_box)
        self.assertIsNot(self.app.map_canvas, self.app.chart_canvas)
        self.app.watch_entry.insert.assert_called_with(0, "Maxima")

    def test_refresh_fills_the_window_and_comes_back(self):
        self.app.refresh()

        self.app.header.configure.assert_called_with(text=header_text(snapshot_of(self.sim)))
        self.assertIn("Maxima  [alive]", self.texts_written(self.app.watch_box)[0])
        self.assertIn("Testville", self.texts_written(self.app.world_box)[0])
        self.assertEqual(7, self.app.tree.insert.call_count)
        self.app.status.configure.assert_called_with(text=f"connected to 127.0.0.1:{self.server.port}")
        self.root.after.assert_called_once_with(250, self.app.refresh)

    def test_second_refresh_replaces_the_rows(self):
        self.app.refresh()
        self.app.refresh()
        self.assertEqual(2, self.app.tree.delete.call_count)
        self.assertEqual(14, self.app.tree.insert.call_count)

    def test_text_boxes_are_read_only_between_updates(self):
        self.app.refresh()
        states = [call.kwargs.get("state") for call in self.app.watch_box.configure.call_args_list]
        # created disabled, opened for the update, closed again
        self.assertEqual(["disabled", "normal", "disabled"], states)

    def test_changing_the_watched_npc(self):
        self.app.watch_entry.get.return_value = "  Alice "
        self.app.set_watch()

        self.assertEqual("Alice", self.app.watch)
        self.assertIn("Alice  [alive]", self.texts_written(self.app.watch_box)[-1])
        self.root.after.assert_not_called()          # no second timer is started

    def test_unknown_npc_is_explained_in_the_window(self):
        self.app.watch_entry.get.return_value = "Zed"
        self.app.set_watch()
        self.assertIn("no npc named 'Zed'", self.texts_written(self.app.watch_box)[-1])

    def test_game_gone_keeps_the_last_picture_and_retries(self):
        self.app.refresh()
        inserts = self.app.tree.insert.call_count
        self.server.stop()

        self.app.refresh()

        self.assertIn("connect", self.app.status.configure.call_args.kwargs["text"])
        self.assertEqual(inserts, self.app.tree.insert.call_count)         # nothing was redrawn
        self.assertEqual(2, self.root.after.call_count)                    # but it will try again

    def test_start_without_game(self):
        self.server.stop()
        app = DisplayApp(self.tk, self.ttk, self.root, GameClient(port=self.server.port, timeout=1), "Maxima")
        app.refresh()
        text = app.status.configure.call_args.kwargs["text"]
        self.assertIn("cannot connect", text)


class TestMain(unittest.TestCase):

    def test_without_tkinter(self):
        import contextlib, io, sys
        err = io.StringIO()
        with mock.patch.dict(sys.modules, {"tkinter": None}), contextlib.redirect_stderr(err):
            self.assertEqual(1, display.main([]))
        self.assertIn("tkinter is not installed", err.getvalue())
        self.assertIn("console.py works without it", err.getvalue())


def real_tk():
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(real_tk(), "needs tkinter and a screen")
class TestRealWindow(unittest.TestCase):

    def test_window_opens_and_shows_the_game(self):
        import tkinter as tk
        from tkinter import ttk

        sim = make_sim()
        sim.run(3)
        server = GameServer(sim, port=0)
        server.start()
        self.addCleanup(server.stop)

        root = tk.Tk()
        self.addCleanup(root.destroy)
        client = GameClient(port=server.port, timeout=2)
        self.addCleanup(client.close)

        app = DisplayApp(tk, ttk, root, client, "Maxima", interval_ms=100000)
        app.refresh(reschedule=False)
        root.update()

        self.assertIn("Maxima", app.watch_box.get("1.0", "end"))
        self.assertIn("Testville", app.header.cget("text"))
        self.assertEqual(7, len(app.tree.get_children()))
        self.assertTrue(app.map_canvas.find_all())


if __name__ == "__main__":
    unittest.main()
