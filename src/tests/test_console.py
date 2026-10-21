
import contextlib
import io
import unittest

import console
from client import GameClient, GameError
from gameserver import GameServer

from townhelper import make_sim


def run(client, *words):
    lines = []
    console.execute(client, list(words), out=lines.append)
    return "\n".join(lines)


class ConsoleTestCase(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)
        for _ in range(5):
            self.sim.step()                 # day 3, AFTERNOON: Maxima shops
        self.server = GameServer(self.sim, port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.client = GameClient(port=self.server.port, timeout=3)
        self.addCleanup(self.client.close)


class TestCommands(ConsoleTestCase):

    def test_where(self):
        text = run(self.client, "where", "maxima")
        self.assertEqual("Maxima: shopping at Shop (shop) [day 3, AFTERNOON]", text)

    def test_location_is_the_same_as_where_also_with_colon(self):
        self.assertEqual(run(self.client, "where", "maxima"), run(self.client, "location", "maxima"))
        self.assertEqual(run(self.client, "where", "maxima"), run(self.client, "location:", "maxima"))

    def test_names_with_spaces_and_case(self):
        self.assertIn("Home Block", run(self.client, "building", "home", "block"))
        self.assertIn("Villa", run(self.client, "BUILDING", "Villa"))

    def test_npc(self):
        text = run(self.client, "npc", "Alice")
        for part in ("Alice  [alive]", "where:", "doing:", "next:", "health 10/10", "money", "inventory: food",
                     "home:      Home Block, unit", "work:      Job (worker)", "shop:      Shop",
                     "routine:   1", "lifetime:", "recent:"):
            self.assertIn(part, text)

    def test_stats_is_the_same_as_npc(self):
        self.assertEqual(run(self.client, "npc", "Alice"), run(self.client, "stats", "Alice"))

    def test_npc_shows_infinite_money_and_no_workplace(self):
        text = run(self.client, "npc", "Maxima")
        self.assertIn("money inf", text)
        self.assertIn("work:      -", text)

    def test_world(self):
        text = run(self.client, "world")
        for part in ("Testville  -  day 3, AFTERNOON", "population: 5 alive, 0 died so far", "last cycle: 2 (0 died, 0 new)", "where:",
                     "buildings:  2 home, 1 shop, 2 tile, 1 work", "today:", "total:", "food bought"):
            self.assertIn(part, text)

    def test_status_is_world(self):
        self.assertEqual(run(self.client, "world"), run(self.client, "status"))

    def test_building_kinds(self):
        self.assertIn("rent:       1000 per day", run(self.client, "building", "Villa"))
        shop = run(self.client, "building", "Shop")
        self.assertIn("food price: 5", shop)
        self.assertIn("revenue", shop)
        self.assertIn("employees:  0/2", shop)
        self.assertIn("working now", run(self.client, "building", "Job"))
        self.assertIn("owner:", run(self.client, "building", "3,3"))
        self.assertIn("citizens:   5", run(self.client, "building", "0,0"))

    def test_buildings(self):
        text = run(self.client, "buildings")
        self.assertEqual(8, len(text.splitlines()))     # header + town hall + 6 buildings
        self.assertIn("Villa", text)
        self.assertIn("1/2 residents", text)
        self.assertIn("3/3 employees", text)

    def test_people(self):
        text = run(self.client, "people", "3", "money")
        self.assertIn("3 of 5 citizens, sorted by money", text)
        self.assertEqual(5, len(text.splitlines()))     # headline + header + 3 people

    def test_goods(self):
        text = run(self.client, "goods", "2")
        self.assertIn("goods and money  -  day 3 running", text)
        self.assertIn("Shop: sold", text)
        self.assertIn("bought", text.splitlines()[-3])

    def test_goods_before_any_day_ended(self):
        client_sim = make_sim()
        client_sim.step()
        server = GameServer(client_sim, port=0)
        server.start()
        self.addCleanup(server.stop)
        client = GameClient(port=server.port, timeout=3)
        self.addCleanup(client.close)

        self.assertIn("no finished day yet", run(client, "goods"))

    def test_map_marks_the_npc(self):
        text = run(self.client, "map", "Maxima")
        shop_row = next(line for line in text.splitlines() if "SH" in line)
        self.assertIn("SH*", shop_row)                  # she is at the shop right now
        self.assertIn("* = Maxima", text)
        self.assertEqual(1, text.count("*") - 1)        # one mark (+ the one in the legend)

    def test_map_without_a_name_marks_nothing(self):
        text = run(self.client, "map")
        self.assertNotIn("*", text)
        self.assertIn("MN", text)
        self.assertIn("TH", text)

    def test_help(self):
        text = run(self.client, "help")
        for command in console.COMMANDS:
            self.assertIn(command, text)

    def test_errors(self):
        with self.assertRaisesRegex(GameError, "no npc named 'Zed'"):
            run(self.client, "where", "Zed")
        with self.assertRaisesRegex(GameError, "unknown command 'dance'"):
            run(self.client, "dance")
        with self.assertRaisesRegex(GameError, "missing argument: npc name"):
            run(self.client, "where")
        with self.assertRaisesRegex(GameError, "missing argument: building"):
            run(self.client, "building")

    def test_output_is_plain_ascii(self):
        # Windows consoles choke on fancy characters
        for words in (["world"], ["npc", "Alice"], ["buildings"], ["goods"], ["map", "Alice"],
                      ["people"], ["building", "Villa"], ["help"]):
            with self.subTest(words=words):
                run(self.client, *words).encode("ascii")


class TestMainFunction(ConsoleTestCase):

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = console.main(["--port", str(self.server.port), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_one_shot(self):
        code, out, _ = self.call("where", "maxima")
        self.assertEqual(0, code)
        self.assertIn("Maxima: shopping", out)

    def test_game_error_exit_code(self):
        code, _, err = self.call("where", "Zed")
        self.assertEqual(1, code)
        self.assertIn("error: no npc named 'Zed'", err)

    def test_no_game_running(self):
        self.server.stop()
        code, _, err = self.call("world")
        self.assertEqual(2, code)
        self.assertIn("Is main.py running?", err)

    def test_interactive(self):
        import builtins
        from unittest import mock

        answers = iter(["where max", "", "dance", "building Zzz", "quit"])
        with mock.patch.object(builtins, "input", lambda prompt="": next(answers)):
            code, out, _ = self.call()

        self.assertEqual(0, code)
        self.assertIn("Maxima: shopping", out)
        self.assertIn("error: unknown command 'dance'", out)      # errors do not end the session
        self.assertIn("error: no building named 'Zzz'", out)


class FakeClient:
    """answers 'npc' with prepared data, like a game that moves on"""

    def __init__(self, answers):
        self.answers = list(answers)

    def request(self, cmd, *args):
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def npc(day, phase, place, action, log=(), money=5, hunger=0, food=1):
    return {
        "name": "Maxima", "alive": True,
        "clock": {"day": day, "phase": phase, "next_phase": "X", "cycle": day - 1},
        "location": {"text": place, "kind": "home", "building": "B", "unit": 0, "address": [0, 0]},
        "action": {"type": action, "text": action.lower(), "phase": phase},
        "stats": {"money": {"value": money, "max": 10}, "hunger": {"value": hunger, "max": 10}},
        "inventory": {"food": food},
        "log": [{"day": d, "phase": p, "text": t} for d, p, t in log],
    }


class TestFollow(unittest.TestCase):

    def follow(self, answers, **kwargs):
        lines = []
        console.follow(FakeClient(answers), "Maxima", out=lines.append, sleep=lambda seconds: None, **kwargs)
        return lines[2:]        # without the two header lines

    def test_prints_a_line_when_something_changes(self):
        lines = self.follow([
            npc(1, "MORNING", "home", "WAKEUP"),
            npc(1, "MORNING", "home", "WAKEUP"),            # nothing changed
            npc(1, "NOON", "shop", "SHOP"),
            npc(1, "NOON", "shop", "SHOP"),
        ], max_updates=2)

        self.assertEqual(2, len(lines))
        self.assertIn("MORNING", lines[0])
        self.assertIn("NOON", lines[1])

    def test_each_event_is_shown_once(self):
        bought = (1, "NOON", "bought 3 food for 15")
        lines = self.follow([
            npc(1, "NOON", "shop", "SHOP", log=[bought]),
            npc(1, "NOON", "shop", "SHOP", log=[bought]),
            npc(1, "EVENING", "home", "SLEEP", log=[bought, (1, "EVENING", "ate 1 food")]),
        ], max_updates=2)

        events = [line for line in lines if "*" in line]
        self.assertEqual(2, len(events))
        self.assertIn("bought 3 food for 15", events[0])
        self.assertIn("ate 1 food", events[1])

    def test_status_line_shows_money_hunger_food(self):
        line = self.follow([npc(2, "NOON", "shop", "SHOP", money=40, hunger=2, food=3)], max_updates=1)[0]
        self.assertIn("money 40 hunger 2 food 3", line)
        self.assertIn("day 2", line)

    def test_stops_when_the_npc_is_gone(self):
        lines = self.follow([npc(1, "NOON", "shop", "SHOP"), GameError("Maxima died in cycle 10 (starvation)")])
        self.assertEqual("stopped: Maxima died in cycle 10 (starvation)", lines[-1])


if __name__ == "__main__":
    unittest.main()
