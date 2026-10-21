"""
The real thing: the game runs as its own program and console.py asks it things
from another program, exactly like you do it.
"""

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
        self.port = free_port()

        kwargs = {}
        if os.name == "posix":      # do not inherit an ignored Ctrl+C from whoever runs the tests
            kwargs["preexec_fn"] = lambda: signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.game = subprocess.Popen(
            [sys.executable, "main.py", "--new", "--delay", "0.01", "--port", str(self.port),
             "--save-file", str(self.save)],
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
        self.assertIn("1002 alive", world.stdout)

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
