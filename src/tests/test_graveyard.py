
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import console
import main
import queries
from client import GameClient, GameError
from gameserver import GameServer
from graveyard import Graveyard, Grave
from persistence import save_state, load_state
from person import Person
from queries import QueryError

from townhelper import make_sim


class TestGraveyard(unittest.TestCase):

    def setUp(self):
        self.yard = Graveyard()
        self.yard.bury("Ann", 3, "starvation")
        self.yard.bury("Bob", 3, "starvation")
        self.yard.bury("Cid", 5, "old age")

    def test_bury(self):
        grave = self.yard.bury("Dan", 6)
        self.assertEqual(Grave("Dan", 6, "unknown"), grave)
        self.assertEqual(4, len(self.yard))

    def test_names_are_stored_as_text(self):
        import uuid
        self.assertEqual("1" * 32, Graveyard().bury(uuid.UUID("1" * 32), 1).name.replace("-", ""))

    def test_order_of_death_is_kept(self):
        self.assertEqual(["Ann", "Bob", "Cid"], [grave.name for grave in self.yard])

    def test_died_in(self):
        self.assertEqual(["Ann", "Bob"], [g.name for g in self.yard.died_in(3)])
        self.assertEqual(["Cid"], [g.name for g in self.yard.died_in(5)])
        self.assertEqual([], self.yard.died_in(4))
        self.assertEqual([], self.yard.died_in(99))
        self.assertEqual([], self.yard.died_in(1))

    def test_latest_is_newest_first(self):
        self.assertEqual(["Cid", "Bob"], [g.name for g in self.yard.latest(2)])
        self.assertEqual(3, len(self.yard.latest(50)))

    def test_find(self):
        self.assertEqual(Grave("Bob", 3, "starvation"), self.yard.find("bob"))
        self.assertEqual("Cid", self.yard.find("CI").name)
        self.assertIsNone(self.yard.find("Zed"))
        self.assertIsNone(self.yard.find(""))

    def test_find_gives_the_newest_when_a_name_is_used_twice(self):
        self.yard.bury("Ann", 9)
        self.assertEqual(9, self.yard.find("Ann").cycle)


class TestBurials(unittest.TestCase):

    def test_the_dead_land_in_the_graveyard_with_cycle_and_cause(self):
        sim = make_sim()
        sim.run(10)         # Dave has no job and starves in cycle 10

        self.assertEqual([Grave("Dave", 10, "starvation")], list(sim.town_hall.graveyard))
        self.assertEqual(1, sim.deaths)

    def test_nobody_is_buried_twice(self):
        sim = make_sim()
        sim.run(15)
        self.assertEqual(1, len(sim.town_hall.graveyard))

    def test_the_living_are_not_in_it(self):
        sim = make_sim()
        sim.run(15)
        names = {grave.name for grave in sim.town_hall.graveyard}
        self.assertTrue({p.name for p in sim.living()}.isdisjoint(names))

    def test_cause_comes_from_the_person(self):
        person = Person(name="X")
        person.die("an accident")
        self.assertFalse(person.alive)
        self.assertEqual("an accident", person.cause_of_death)

        starving = Person(name="Y")
        starving.attributes.hunger = starving.attributes.max_hunger
        starving.check()
        self.assertEqual("starvation", starving.cause_of_death)

    def test_graveyard_survives_save_and_load(self):
        sim = make_sim()
        sim.run(12)
        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        self.assertEqual(list(sim.town_hall.graveyard), list(loaded.town_hall.graveyard))
        self.assertEqual(1, loaded.deaths)


class TestNewcomers(unittest.TestCase):

    def test_founders_are_not_new(self):
        sim = make_sim()
        sim.run_cycle()
        self.assertEqual(0, sim.last_cycle()["new"])

    def test_somebody_who_arrives_is_new_in_that_cycle_only(self):
        sim = make_sim()
        sim.run(2)

        sim.town_hall.add_citizen(Person(name="Newbie"))
        sim.run_cycle()
        self.assertEqual({"cycle": 3, "died": 0, "new": 1}, sim.last_cycle())

        sim.run_cycle()
        self.assertEqual({"cycle": 4, "died": 0, "new": 0}, sim.last_cycle())

    def test_arriving_during_a_cycle_counts_for_that_cycle(self):
        sim = make_sim()
        sim.run(1)
        for _ in range(4):
            sim.step()
        sim.town_hall.add_citizen(Person(name="Midday"))
        sim.run_cycle()

        self.assertEqual(2, sim.last_cycle()["cycle"])
        self.assertEqual(1, sim.last_cycle()["new"])

    def test_several_and_no_double_counting(self):
        sim = make_sim()
        sim.run(1)
        newbies = [Person(name=f"N{i}") for i in range(3)]
        for person in newbies + newbies[:1]:      # the first one is added twice
            sim.town_hall.add_citizen(person)
        sim.run_cycle()

        self.assertEqual(3, sim.last_cycle()["new"])

    def test_history_has_died_and_new_for_every_cycle(self):
        sim = make_sim()
        sim.run(9)
        sim.town_hall.add_citizen(Person(name="Newbie"))
        sim.run(2)

        history = {entry["day"]: entry for entry in sim.town_hall.ledger.history}
        self.assertEqual((0, 0), (history[9]["died"], history[9]["new"]))
        self.assertEqual((1, 1), (history[10]["died"], history[10]["new"]))   # Dave died, Newbie arrived
        self.assertEqual((1, 0), (history[10]["died"], history[11]["new"]))

    def test_last_cycle_before_anything_happened(self):
        self.assertEqual({"cycle": 0, "died": 0, "new": 0}, make_sim().last_cycle())


class TestLogLine(unittest.TestCase):

    def lines(self, cycles, newcomers_in_cycle=None):
        sim = make_sim()
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out):
            for number in range(1, cycles + 1):
                if number == newcomers_in_cycle:
                    sim.town_hall.add_citizen(Person(name="Newbie"))
                main.run_cycles(sim, 1, Path(tmp) / "save.pkl")
        return out.getvalue().splitlines()

    def test_shows_what_happened_in_this_cycle_not_the_total(self):
        lines = self.lines(12)

        self.assertTrue(lines[8].startswith("cycle 9: alive 5, died 0, new 0,"), lines[8])
        self.assertTrue(lines[9].startswith("cycle 10: alive 4, died 1, new 0,"), lines[9])
        self.assertTrue(lines[10].startswith("cycle 11: alive 4, died 0, new 0,"), lines[10])      # not "1" again
        self.assertTrue(lines[11].startswith("cycle 12: alive 4, died 0, new 0,"), lines[11])
        self.assertFalse(any("deaths" in line for line in lines))

    def test_shows_the_new_ones(self):
        lines = self.lines(4, newcomers_in_cycle=3)

        self.assertIn("new 0", lines[1])
        self.assertTrue(lines[2].startswith("cycle 3: alive 6, died 0, new 1,"), lines[2])
        self.assertIn("new 0", lines[3])

    def test_line_still_has_food_and_revenue(self):
        self.assertRegex(self.lines(1)[0], r"^cycle 1: alive 5, died 0, new 0, homeless 0, food \d+, shop revenue \d+$")


class TestGraveyardQuery(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(10)

    def ask(self, *args):
        return queries.run(self.sim, "graveyard", list(args))

    def test_default(self):
        data = self.ask()
        self.assertEqual({"total": 1, "shown": 1, "graves": [{"name": "Dave", "cycle": 10, "cause": "starvation"}]}, data)

    def test_limit_and_all(self):
        for number in range(30):
            self.sim.town_hall.graveyard.bury(f"X{number}", 11)

        self.assertEqual(20, self.ask()["shown"])
        self.assertEqual(3, self.ask("3")["shown"])
        self.assertEqual(31, self.ask("all")["shown"])
        self.assertEqual(31, self.ask("ALL")["total"])
        self.assertEqual("X29", self.ask("2")["graves"][0]["name"])          # newest first

    def test_answers_stay_small_enough(self):
        for number in range(queries.MAX_GRAVES + 100):
            self.sim.town_hall.graveyard.bury("x" * 36, 11)

        data = self.ask("all")
        self.assertEqual(queries.MAX_GRAVES, data["shown"])
        self.assertEqual(queries.MAX_GRAVES + 101, data["total"])
        self.assertEqual(queries.MAX_GRAVES, self.ask("999999")["shown"])

    def test_bad_arguments(self):
        for bad in ("many", "0", "-3"):
            with self.subTest(argument=bad), self.assertRaises(QueryError):
                self.ask(bad)

    def test_empty(self):
        self.assertEqual({"total": 0, "shown": 0, "graves": []}, queries.run(make_sim(), "graveyard", []))

    def test_world_knows_the_last_cycle_and_the_recent_dead(self):
        world = queries.run(self.sim, "world", [])

        self.assertEqual({"cycle": 10, "died": 1, "new": 0}, world["last_cycle"])
        self.assertEqual([{"name": "Dave", "cycle": 10, "cause": "starvation"}], world["recent_deaths"])
        self.assertEqual(1, world["population"]["deaths"])

    def test_asking_for_a_dead_npc(self):
        with self.assertRaisesRegex(QueryError, r"Dave died in cycle 10 \(starvation\)"):
            queries.run(self.sim, "npc", ["dav"])


class TestGraveyardConsole(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(10)
        self.server = GameServer(self.sim, port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.client = GameClient(port=self.server.port, timeout=3)
        self.addCleanup(self.client.close)

    def console_out(self, *words):
        lines = []
        console.execute(self.client, list(words), out=lines.append)
        return "\n".join(lines)

    def test_graveyard(self):
        text = self.console_out("graveyard")
        self.assertEqual(["graveyard: 1 buried", "cycle  name  cause", "10     Dave  starvation"],
                         text.splitlines())

    def test_aliases(self):
        self.assertEqual(self.console_out("graveyard"), self.console_out("dead"))
        self.assertEqual(self.console_out("graveyard"), self.console_out("graves"))

    def test_hint_when_there_are_more_than_shown(self):
        for number in range(25):
            self.sim.town_hall.graveyard.bury(f"X{number}", 11)
        text = self.console_out("graveyard")

        self.assertIn("26 buried, showing the 20 most recent", text)
        self.assertIn("'graveyard all'", text)
        self.assertEqual(2 + 20, len(text.splitlines()))
        self.assertEqual(2 + 26, len(self.console_out("graveyard", "all").splitlines()))
        self.assertNotIn("showing", self.console_out("graveyard", "all"))

    def test_empty_graveyard(self):
        sim = make_sim()
        server = GameServer(sim, port=0)
        server.start()
        self.addCleanup(server.stop)
        client = GameClient(port=server.port, timeout=3)
        self.addCleanup(client.close)

        lines = []
        console.execute(client, ["graveyard"], out=lines.append)
        self.assertEqual(["the graveyard is empty"], lines)

    def test_bad_number(self):
        with self.assertRaises(GameError):
            self.console_out("graveyard", "lots")

    def test_world_shows_last_cycle_and_the_dead_with_their_cycle(self):
        text = self.console_out("world")
        self.assertIn("last cycle: 10 (1 died, 0 new)", text)
        self.assertIn("last deaths: Dave (cycle 10)", text)

    def test_help_lists_it(self):
        self.assertIn("graveyard", self.console_out("help"))

    def test_plain_ascii(self):
        self.console_out("graveyard").encode("ascii")


if __name__ == "__main__":
    unittest.main()
