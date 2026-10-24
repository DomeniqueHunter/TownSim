"""
The real thing: the game runs as its own program and console.py asks it things
from another program, exactly like you do it.
"""

import json
import os
import random
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from client import GameClient, GameConnectionError
from persistence import load_state

SRC = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.save = Path(tmp.name) / "save.pkl"
        self.items_dir = Path(tmp.name) / "items"       # never the real items folder of the game
        self.port = free_port()

        kwargs = {}
        if os.name == "posix":      # do not inherit an ignored Ctrl+C from whoever runs the tests
            kwargs["preexec_fn"] = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.game = subprocess.Popen(
            [sys.executable, "main.py", "--new", "--delay", "0.01", "--port", str(self.port),
             "--save-file", str(self.save), "--items-dir", str(self.items_dir)],
            cwd=SRC, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)
        self.addCleanup(self.kill_game)

        self.client = GameClient(port=self.port, timeout=5)
        self.addCleanup(self.client.close)
        self.wait_until_it_answers()

    def kill_game(self):
        if self.game.poll() is None:
            self.game.kill()
        self.game.communicate()

    def wait_until_it_answers(self):
        deadline = time.time() + 30
        while True:
            try:
                self.client.request("ping")
                return
            except GameConnectionError:
                if self.game.poll() is not None:
                    self.fail("the game stopped:\n" + self.game.communicate()[0])
                if time.time() > deadline:
                    self.fail("the game does not answer")
                time.sleep(0.1)

    def saved_cycle(self) -> int:
        """cycle stored in the save file (writing is atomic, so reading it at any time is safe)"""
        if not self.save.exists():
            return -1
        state = random.getstate()           # load_state() would replace the random state of this process
        try:
            return load_state(self.save).cycle
        finally:
            random.setstate(state)

    def console(self, *words):
        return subprocess.run([sys.executable, "console.py", "--port", str(self.port), *words],
                              cwd=SRC, capture_output=True, text=True, timeout=30)

    def test_console_asks_the_running_game(self):
        where = self.console("where", "maxima")
        self.assertEqual(0, where.returncode, where.stderr)
        self.assertRegex(where.stdout, r"^Maxima: .+ at .+ \[day \d+, [A-Z_]+\]$")

        npc = self.console("stats", "Maxima")
        self.assertIn("Maxima  [alive]", npc.stdout)
        self.assertIn("money inf", npc.stdout)

        world = self.console("world")
        self.assertIn("Small Ville", world.stdout)
        self.assertRegex(world.stdout, r"\d+ alive")

        shop = self.console("building", "Corner Shop")
        self.assertIn("food price: 5", shop.stdout)

        self.assertIn("Villa Maxima", self.console("building", "5,5").stdout)

        bad = self.console("where", "nobody")
        self.assertEqual(1, bad.returncode)
        self.assertIn("no npc named 'nobody'", bad.stderr)

    def test_the_game_really_moves_on_while_we_look(self):
        def now():
            clock = self.client.request("world")["clock"]
            return clock["cycle"], clock["phase"]

        first = now()
        deadline = time.time() + 15
        while now() == first:
            self.assertLess(time.time(), deadline, "time does not pass")
            time.sleep(0.05)

    def test_goods_are_counted(self):
        deadline = time.time() + 30
        while self.client.request("goods")["history"] == []:
            self.assertLess(time.time(), deadline, "no day was finished")
            time.sleep(0.1)

        goods = self.console("goods", "3")
        self.assertIn("Corner Shop: sold", goods.stdout)
        data = self.client.request("goods")
        self.assertGreater(data["total"]["food_bought"], 0)
        self.assertGreater(data["total"]["food_eaten"], 0)
        self.assertGreater(data["total"]["wages_paid"], 0)

    def wait_for(self, condition, what, seconds=30):
        deadline = time.time() + seconds
        while not condition():
            self.assertLess(time.time(), deadline, f"timeout: {what}")
            time.sleep(0.1)

    def consumed(self, name):
        return sorted(p.name for p in self.items_dir.glob(f"_consumed_{name}_*.json"))

    def test_dropping_a_file_puts_new_items_into_the_game(self):
        self.wait_for(self.items_dir.is_dir, "the game makes the items folder")
        (self.items_dir / "bread.json").write_text(json.dumps({"format": 1, "items": [
            {"id": "bread", "name": "Bread", "category": "food", "price": 3, "stock": 100000,
             "effects": {"hunger": -2}, "description": "Fresh from the bakery."}]}))

        self.wait_for(lambda: self.consumed("bread"), "the file is taken over and renamed")

        self.assertFalse((self.items_dir / "bread.json").exists())
        self.assertRegex(self.consumed("bread")[0], r"^_consumed_bread_\d+\.json$")
        items = self.console("items")
        self.assertEqual(0, items.returncode, items.stderr)
        self.assertRegex(items.stdout, r"bread\s+Bread\s+food\s+hunger -2\s+1 piece\s+Corner Shop 3 \(\d+ left\)")
        shop = self.console("building", "Corner Shop")
        self.assertIn("bread 3 (", shop.stdout)

        # and the sims really use it: the pieces in the shop go down
        def pieces_left():
            return next(i for i in self.client.request("items")["items"] if i["id"] == "bread")["offers"][0]["quantity"]
        self.wait_for(lambda: pieces_left() < 100000, "the sims buy the bread")

    def test_a_tanker_of_milk_is_split_into_bottles(self):
        self.wait_for(self.items_dir.is_dir, "the game makes the items folder")
        (self.items_dir / "milk.json").write_text(json.dumps({"format": 1, "items": [
            {"id": "milk", "name": "Milk bottle", "category": "food", "price": 2, "unit": "l", "portion": 1,
             "stock": 1000000, "effects": {"hunger": -2}}]}))

        self.wait_for(lambda: self.consumed("milk"), "the file is taken over")

        items = self.console("items")
        self.assertEqual(0, items.returncode, items.stderr)
        self.assertRegex(items.stdout, r"milk\s+Milk bottle\s+food\s+hunger -2\s+1 l\s+Corner Shop 2 \(\d+ left\)")
        shelf = self.console("building", "Corner Shop")
        self.assertRegex(shelf.stdout, r"milk 2 \(\d+ left, 1 l each\)")

        # the sims buy bottles out of the tanker, one number goes down
        def litres_left():
            offers = next(i for i in self.client.request("items")["items"] if i["id"] == "milk")["offers"]
            return offers[0]["quantity"]
        self.wait_for(lambda: litres_left() < 1000000, "the sims buy milk")

    def test_an_invalid_file_stays_until_it_is_fixed(self):
        self.wait_for(self.items_dir.is_dir, "the game makes the items folder")
        path = self.items_dir / "cake.json"
        path.write_text('{"format": 1, "items": [{"id": "cake", "name": "Cake", "category": "food", '
                        '"price": "3", "stock": 5, "effects": {"hunger": -3}}]}')

        time.sleep(4)                       # plenty of time to look at it
        self.assertTrue(path.exists())
        self.assertEqual([], self.consumed("cake"))
        self.assertNotIn("cake", self.console("items").stdout)

        path.write_text('{"format": 1, "items": [{"id": "cake", "name": "Cake", "category": "food", '
                        '"price": 3, "stock": 5, "effects": {"hunger": -3}}]}')
        self.wait_for(lambda: self.consumed("cake"), "the fixed file is taken over")
        self.assertIn("cake", self.console("items").stdout)

    def test_a_gift_lands_in_the_inventory_of_maxima(self):
        self.wait_for(self.items_dir.is_dir, "the game makes the items folder")
        (self.items_dir / "gift.json").write_text(json.dumps({"format": 1, "items": [
            {"id": "golden_apple", "name": "Golden Apple", "category": "food", "price": 0, "stock": 1,
             "effects": {"hunger": -5, "health": 2}, "deliver_to": "Maxima"}]}))

        self.wait_for(lambda: self.consumed("gift"), "the gift is taken over")

        npc = self.console("npc", "Maxima")
        self.assertIn("golden_apple 1", npc.stdout)
        self.assertIn("received 1 Golden Apple as a gift", npc.stdout)

    def test_the_items_are_in_the_save_file(self):
        self.wait_for(self.items_dir.is_dir, "the game makes the items folder")
        (self.items_dir / "bread.json").write_text(json.dumps({"format": 1, "items": [
            {"id": "bread", "name": "Bread", "category": "food", "price": 3, "stock": 100000,
             "effects": {"hunger": -2}}]}))
        self.wait_for(lambda: self.consumed("bread"), "the file is taken over")

        # the file is renamed after the save, so the save has the items at this point
        state = random.getstate()
        try:
            loaded = load_state(self.save)
        finally:
            random.setstate(state)
        self.assertIn("bread", loaded.town_hall.catalog)
        self.assertIn("bread", loaded.town_hall.shop_buildings[0].stock)

    @unittest.skipUnless(os.name == "posix", "needs Ctrl+C (SIGINT)")
    def test_ctrl_c_stops_the_game_and_the_state_was_saved(self):
        # wait until a finished cycle is really in the save FILE (the game saves a moment after
        # the cycle is over, a Ctrl+C in between correctly falls back to the previous save)
        deadline = time.time() + 30
        while self.saved_cycle() < 1:
            self.assertLess(time.time(), deadline)
            time.sleep(0.1)

        self.game.send_signal(signal.SIGINT)
        output = self.game.communicate(timeout=30)[0]

        self.assertEqual(0, self.game.returncode, output)
        self.assertIn("stopped, last saved state: cycle", output)
        self.assertGreaterEqual(load_state(self.save).cycle, 1)

        # and now nobody answers anymore
        result = self.console("world")
        self.assertEqual(2, result.returncode)
        self.assertIn("Is main.py running?", result.stderr)


if __name__ == "__main__":
    unittest.main()
