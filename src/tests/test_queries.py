
import json
import unittest

import queries
from queries import QueryError

from townhelper import make_sim


def ask(sim, cmd, *args):
    return queries.run(sim, cmd, list(args))


class QueryTestCase(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)
        for _ in range(4):
            self.sim.step()      # day 3, somewhere in the middle of the day


class TestFindingPeople(QueryTestCase):

    def test_exact_name_any_case(self):
        self.assertEqual("Maxima", ask(self.sim, "where", "maxima")["name"])
        self.assertEqual("Maxima", ask(self.sim, "where", "MAXIMA")["name"])

    def test_prefix(self):
        self.assertEqual("Maxima", ask(self.sim, "where", "max")["name"])

    def test_ambiguous_prefix(self):
        with self.assertRaisesRegex(QueryError, "2 npcs match 'Al'"):
            ask(self.sim, "where", "Al")

    def test_exact_name_beats_longer_names(self):
        self.assertEqual("Bob", ask(self.sim, "where", "Bob")["name"])

    def test_unknown_name_keeps_what_was_typed(self):
        with self.assertRaisesRegex(QueryError, "no npc named 'Zed'"):
            ask(self.sim, "where", "Zed")

    def test_empty_name(self):
        with self.assertRaises(QueryError):
            ask(self.sim, "npc")

    def test_dead_npc_is_reported_as_dead(self):
        self.sim.run(8)       # Dave starves on day 10
        with self.assertRaisesRegex(QueryError, "Dave died in cycle 10 \\(starvation\\)"):
            ask(self.sim, "npc", "Dave")


class TestNpc(QueryTestCase):

    def test_where(self):
        # setup stops after the 4th phase of day 3: Maxima (routine 1) is on her way to the shop
        data = ask(self.sim, "where", "Maxima")

        self.assertTrue(data["alive"])
        self.assertEqual("shop", data["location"]["kind"])
        self.assertEqual("Shop", data["location"]["building"])
        self.assertEqual("GO_TO_SHOP", data["action"]["type"])
        self.assertEqual("on the way to the shop", data["action"]["text"])
        self.assertEqual(3, data["clock"]["day"])
        self.assertEqual(data["action"]["phase"], data["clock"]["phase"])

    def test_where_at_home(self):
        while ask(self.sim, "where", "Maxima")["action"]["type"] != "SLEEP":
            self.sim.step()

        data = ask(self.sim, "where", "Maxima")
        self.assertEqual("home", data["location"]["kind"])
        self.assertEqual("Villa", data["location"]["building"])
        self.assertEqual(0, data["location"]["unit"])
        self.assertEqual([5, 5], data["location"]["address"])
        self.assertEqual("Villa (home, unit 0)", data["location"]["text"])

    def test_npc_details(self):
        data = ask(self.sim, "npc", "Alice")

        self.assertEqual("Alice", data["name"])
        self.assertEqual(1, data["routine"])
        self.assertEqual({"building": "Job", "role": "worker", "address": data["workplace"]["address"]},
                         data["workplace"])
        self.assertEqual("Shop", data["shop"]["building"])
        self.assertEqual("Home Block", data["home"]["building"])
        self.assertEqual({"value": 10, "max": 10}, data["stats"]["health"])
        self.assertEqual(float("inf"), ask(self.sim, "npc", "Maxima")["stats"]["money"]["value"])
        self.assertGreater(data["totals"]["money_earned"], 0)
        self.assertTrue(data["log"])
        self.assertEqual({"day", "phase", "text"}, set(data["log"][0]))

    def test_next_is_what_the_routine_says(self):
        data = ask(self.sim, "npc", "Alice")
        self.assertEqual(self.sim.phase.name, data["next"]["phase"])
        self.assertEqual(self.sim.town_hall.citizens[0].routine[self.sim.phase].name, data["next"]["action"])

    def test_before_the_first_step(self):
        sim = make_sim()
        data = ask(sim, "where", "Alice")

        self.assertEqual("nowhere", data["location"]["kind"])
        self.assertIsNone(data["action"]["type"])
        self.assertIsNone(data["clock"]["phase"])

    def test_missing_place_is_explained(self):
        # nobody has a leisure place yet: the text says so instead of lying
        sim = make_sim()
        maxima = next(p for p in sim.town_hall.citizens if p.name == "Maxima")
        while maxima.current_action is None or maxima.current_action.name != "LEISURE":
            sim.step()

        text = ask(sim, "where", "Maxima")["action"]["text"]
        self.assertIn("relaxing", text)
        self.assertIn("no leisure place", text)

    def test_jobless_person_has_no_workplace(self):
        data = ask(self.sim, "npc", "Dave")
        self.assertIsNone(data["workplace"])

    def test_phase_names_follow_the_game(self):
        # whatever the phase list looks like, clock and next phase use its names
        from person import DayTime
        names = {phase.name for phase in DayTime}
        data = ask(self.sim, "npc", "Alice")
        self.assertIn(data["clock"]["phase"], names)
        self.assertIn(data["next"]["phase"], names)


class TestWorldAndBuildings(QueryTestCase):

    def test_world(self):
        data = ask(self.sim, "world")

        self.assertEqual("Testville", data["town"])
        self.assertEqual(5, data["population"]["alive"])
        self.assertEqual(5, sum(data["census"].values()))
        self.assertEqual({"home": 2, "work": 1, "shop": 1, "tile": 2}, data["buildings"])
        self.assertGreater(data["total"]["food_bought"], 0)
        self.assertEqual(self.sim.totals(), data["totals"])

    def test_buildings_list(self):
        data = ask(self.sim, "buildings")
        names = [b["name"] for b in data["buildings"]]

        self.assertEqual("Testville", names[0])
        self.assertIn("Villa", names)
        self.assertEqual(7, len(names))
        villa = next(b for b in data["buildings"] if b["name"] == "Villa")
        self.assertEqual((1, 2), (villa["residents"], villa["capacity"]))

    def test_building_by_name_part(self):
        self.assertEqual("Villa", ask(self.sim, "building", "villa")["name"])

    def test_building_by_address(self):
        self.assertEqual("Villa", ask(self.sim, "building", "5,5")["name"])
        self.assertEqual("Villa", ask(self.sim, "building", "(5, 5)")["name"])
        self.assertEqual("Testville", ask(self.sim, "building", "0,0")["name"])

    def test_nothing_at_address(self):
        with self.assertRaisesRegex(QueryError, "nothing is built at 9,9"):
            ask(self.sim, "building", "9,9")

    def test_ambiguous_building(self):
        with self.assertRaisesRegex(QueryError, "2 buildings match 'grass'"):
            ask(self.sim, "building", "grass")
        self.assertEqual([3, 3], ask(self.sim, "building", "3,3")["address"])

    def test_unknown_building(self):
        with self.assertRaises(QueryError):
            ask(self.sim, "building", "castle")

    def test_home_details(self):
        data = ask(self.sim, "building", "Villa")

        self.assertEqual("home", data["kind"])
        self.assertEqual(1000, data["rent"])
        self.assertEqual(1, data["residents"])
        self.assertEqual({"health": 5, "stamina": 10, "hunger": -3}, data["gain"])

    def test_shop_details(self):
        data = ask(self.sim, "building", "Shop")

        self.assertEqual("shop", data["kind"])
        self.assertEqual(5, data["food_price"])
        self.assertEqual(data["sold"] * 5, data["revenue"])
        self.assertGreater(data["sold"], 0)

    def test_workplace_details(self):
        data = ask(self.sim, "building", "Job")

        self.assertEqual("work", data["kind"])
        self.assertEqual((3, 3), (data["employees"], data["capacity"]))
        self.assertLessEqual(data["working_now"], data["present"])

    def test_tile_and_townhall_details(self):
        self.assertEqual("tile", ask(self.sim, "building", "3,3")["kind"])
        town = ask(self.sim, "building", "0,0")
        self.assertEqual(("townhall", 5), (town["kind"], town["citizens"]))

    def test_present_names_match_the_census(self):
        sim = self.sim
        here = sum(b["present"] for b in ask(sim, "buildings")["buildings"])
        self.assertEqual(5, here)


class TestListsAndNumbers(QueryTestCase):

    def test_people_sorted_by_hunger_by_default(self):
        data = ask(self.sim, "people")
        hungers = [p["hunger"] for p in data["people"]]

        self.assertEqual(5, data["total"])
        self.assertEqual(sorted(hungers, reverse=True), hungers)

    def test_people_limit_and_money_sort(self):
        data = ask(self.sim, "people", "2", "money")

        self.assertEqual(2, len(data["people"]))
        self.assertEqual("Maxima", data["people"][0]["name"])      # infinite money first
        self.assertEqual("money", data["sort"])

    def test_people_sorted_by_name(self):
        names = [p["name"] for p in ask(self.sim, "people", "10", "name")["people"]]
        self.assertEqual(sorted(names), names)

    def test_people_bad_arguments(self):
        with self.assertRaises(QueryError):
            ask(self.sim, "people", "many")
        with self.assertRaises(QueryError):
            ask(self.sim, "people", "5", "beauty")

    def test_goods(self):
        data = ask(self.sim, "goods", "2")

        self.assertEqual(3, data["day"])
        self.assertEqual([1, 2], [h["day"] for h in data["history"]][-2:])
        self.assertEqual(2, len(data["history"]))
        self.assertEqual("Shop", data["shops"][0]["name"])
        self.assertEqual(data["total"]["food_bought"] - data["total"]["food_eaten"], data["food_stock"])

    def test_goods_bad_argument(self):
        with self.assertRaises(QueryError):
            ask(self.sim, "goods", "lots")

    def test_map(self):
        data = ask(self.sim, "map")
        cells = {tuple(c["pos"]): c for c in data["cells"]}

        self.assertEqual({"min_y": -3, "max_y": 5, "min_x": -3, "max_x": 5}, data["bounds"])
        self.assertEqual("Villa", cells[(5, 5)]["name"])
        self.assertEqual("MN", cells[(5, 5)]["symbol"])
        self.assertEqual("townhall", cells[(0, 0)]["kind"])
        self.assertEqual(7, len(cells))

    def test_snapshot(self):
        data = ask(self.sim, "snapshot", "Maxima")

        self.assertEqual({"world", "goods", "map", "buildings", "watch", "watch_error"}, set(data))
        self.assertEqual("Maxima", data["watch"]["name"])
        self.assertIsNone(data["watch_error"])

    def test_snapshot_without_or_with_bad_watch(self):
        data = ask(self.sim, "snapshot")
        self.assertIsNone(data["watch"])
        self.assertIsNone(data["watch_error"])

        data = ask(self.sim, "snapshot", "Zed")
        self.assertIsNone(data["watch"])
        self.assertIn("no npc named 'Zed'", data["watch_error"])


class TestDispatch(QueryTestCase):

    def test_unknown_command(self):
        with self.assertRaisesRegex(QueryError, "unknown command 'dance'"):
            ask(self.sim, "dance")

    def test_every_answer_can_be_sent_as_json(self):
        for cmd, args in [("ping", []), ("world", []), ("npc", ["Maxima"]), ("where", ["Alice"]),
                          ("people", []), ("buildings", []), ("building", ["Shop"]), ("goods", []),
                          ("map", []), ("snapshot", ["Maxima"])]:
            with self.subTest(cmd=cmd):
                text = json.dumps(queries.run(self.sim, cmd, args))
                self.assertEqual(json.loads(text), queries.run(self.sim, cmd, args))

    def test_queries_do_not_change_the_game(self):
        before = (self.sim.totals(), self.sim.clock(), [str(p) for p in self.sim.town_hall.citizens])
        for cmd in queries.COMMANDS:
            try:
                queries.run(self.sim, cmd, ["Maxima"] if cmd in ("npc", "where", "snapshot") else
                            ["Shop"] if cmd == "building" else [])
            except QueryError:
                pass
        after = (self.sim.totals(), self.sim.clock(), [str(p) for p in self.sim.town_hall.citizens])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
