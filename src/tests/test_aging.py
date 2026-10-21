
import json
import math
import tempfile
import unittest
from pathlib import Path

import console
import queries
from graveyard import Grave
from persistence import save_state, load_state
from person import Person
from person.maxima import Maxima
from person.person import LIFESPAN_RANGE

from townhelper import make_sim


def named(sim, name):
    return next(p for p in sim.town_hall.citizens if p.name == name)


class TestLifespan(unittest.TestCase):

    def test_range_is_90_to_110(self):
        self.assertEqual((90, 110), LIFESPAN_RANGE)

    def test_random_lifespans_cover_the_whole_range_and_nothing_else(self):
        lifespans = {Person().lifespan for _ in range(3000)}
        self.assertEqual(set(range(90, 111)), lifespans)

    def test_lifespans_are_whole_numbers(self):
        self.assertTrue(all(isinstance(Person().lifespan, int) for _ in range(50)))

    def test_a_new_person_is_not_old(self):
        self.assertEqual(0, Person().age)

    def test_age_and_lifespan_can_be_chosen(self):
        person = Person(age=7, lifespan=42)
        self.assertEqual((7, 42), (person.age, person.lifespan))

    def test_nonsense_values(self):
        with self.assertRaises(ValueError):
            Person(age=-1)
        for bad in (0, -5):
            with self.subTest(lifespan=bad), self.assertRaises(ValueError):
                Person(lifespan=bad)

    def test_maxima_lives_forever(self):
        maxima = Maxima()
        self.assertEqual(math.inf, maxima.lifespan)

        maxima.age = 10 ** 9
        self.assertTrue(maxima.check())
        self.assertIsNone(maxima.cause_of_death)

    def test_nobody_else_is_immortal(self):
        self.assertTrue(all(Person().lifespan < math.inf for _ in range(20)))


class TestDyingOfOldAge(unittest.TestCase):

    def test_grow_older(self):
        person = Person()
        person.grow_older()
        person.grow_older()
        self.assertEqual(2, person.age)

    def test_dies_when_the_age_reaches_the_lifespan(self):
        person = Person(lifespan=5)
        person.age = 4
        self.assertTrue(person.check())

        person.grow_older()
        self.assertFalse(person.check())
        self.assertFalse(person.alive)
        self.assertEqual("old age", person.cause_of_death)

    def test_older_than_the_lifespan_is_dead_too(self):
        person = Person(age=50, lifespan=5)
        self.assertFalse(person.check())

    def test_hunger_is_named_when_both_happen_at_once(self):
        person = Person(age=5, lifespan=5)
        person.attributes.hunger = person.attributes.max_hunger
        person.check()
        self.assertEqual("starvation", person.cause_of_death)

    def test_the_dead_stay_dead_and_keep_their_cause(self):
        person = Person(age=5, lifespan=5)
        person.check()
        person.attributes.hunger = person.attributes.max_hunger

        self.assertFalse(person.check())
        self.assertEqual("old age", person.cause_of_death)


class TestAgingInTheSimulation(unittest.TestCase):

    def test_everybody_gets_one_cycle_older_per_cycle(self):
        sim = make_sim()
        sim.run(3)

        self.assertEqual([3] * 5, [p.age for p in sim.living()])        # Maxima too

    def test_age_does_not_change_inside_a_cycle(self):
        sim = make_sim()
        for _ in range(9):
            sim.step()
        self.assertEqual({0}, {p.age for p in sim.living()})
        sim.step()
        self.assertEqual({1}, {p.age for p in sim.living()})

    def test_dies_at_the_end_of_the_cycle_that_equals_its_lifespan(self):
        sim = make_sim()
        alice = named(sim, "Alice")
        alice.lifespan = 5

        sim.run(4)
        self.assertTrue(alice.alive)
        sim.run(1)
        self.assertFalse(alice.alive)

        self.assertEqual([Grave("Alice", 5, "old age")], list(sim.town_hall.graveyard))

    def test_old_age_shows_up_in_the_cycle_numbers(self):
        sim = make_sim()
        named(sim, "Bob").lifespan = 4
        sim.run(4)

        self.assertEqual({"cycle": 4, "died": 1, "new": 0}, sim.last_cycle())
        self.assertEqual(4, sim.totals()["alive"])

    def test_dying_of_age_frees_home_and_job(self):
        sim = make_sim()
        alice = named(sim, "Alice")
        alice.lifespan = 2
        home, job = alice.home, alice.workplace
        sim.run(2)

        self.assertNotIn(alice, home.owners)
        self.assertNotIn(alice, job.employees)
        self.assertNotIn(alice, sim.town_hall.citizens)

    def test_maxima_outlives_everybody(self):
        sim = make_sim()
        for person in sim.town_hall.citizens:
            if person.name != "Maxima":
                person.lifespan = 3
        sim.run(30)

        self.assertEqual(["Maxima"], [p.name for p in sim.living()])
        self.assertEqual(30, named(sim, "Maxima").age)
        self.assertEqual({("Alice", 3, "old age"), ("Alma", 3, "old age"), ("Bob", 3, "old age"),
                          ("Dave", 3, "old age")}, set(sim.town_hall.graveyard))

    def test_a_town_with_random_lifespans_dies_out_between_cycle_90_and_110(self):
        sim = make_sim()          # Alice, Alma, Bob work, Dave has no job, Maxima is immortal
        sim.run(115)

        graves = {grave.name: grave for grave in sim.town_hall.graveyard}
        self.assertEqual({"Alice", "Alma", "Bob", "Dave"}, set(graves))
        self.assertEqual(("starvation", 10), (graves["Dave"].cause, graves["Dave"].cycle))
        for name in ("Alice", "Alma", "Bob"):
            with self.subTest(name=name):
                self.assertEqual("old age", graves[name].cause)
                self.assertTrue(90 <= graves[name].cycle <= 110, graves[name])

        self.assertEqual(["Maxima"], [p.name for p in sim.living()])

    def test_age_and_lifespan_survive_saving(self):
        sim = make_sim()
        sim.run(7)
        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        def ages(s):
            return {p.name: (p.age, p.lifespan) for p in s.town_hall.citizens}

        self.assertEqual(ages(sim), ages(loaded))
        self.assertEqual(math.inf, ages(loaded)["Maxima"][1])


class TestAgeInQueriesAndConsole(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(3)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_npc_has_age_and_lifespan(self):
        alice = self.ask("npc", "Alice")["stats"]["age"]
        self.assertEqual(3, alice["value"])
        self.assertEqual(named(self.sim, "Alice").lifespan, alice["max"])
        self.assertTrue(90 <= alice["max"] <= 110)

        self.assertEqual({"value": 3, "max": math.inf}, self.ask("npc", "Maxima")["stats"]["age"])

    def test_everything_can_still_be_sent_as_json(self):
        data = self.ask("npc", "Maxima")
        self.assertEqual(math.inf, json.loads(json.dumps(data))["stats"]["age"]["max"])

    def test_people_show_the_age(self):
        self.assertTrue(all(p["age"] == 3 for p in self.ask("people")["people"]))

    def test_people_sorted_by_age_oldest_first(self):
        named(self.sim, "Bob").age = 50
        named(self.sim, "Dave").age = 20
        data = self.ask("people", "3", "age")

        self.assertEqual("age", data["sort"])
        self.assertEqual(["Bob", "Dave"], [p["name"] for p in data["people"]][:2])
        self.assertEqual([50, 20, 3], [p["age"] for p in data["people"]])

    def test_the_sort_error_names_age(self):
        with self.assertRaisesRegex(queries.QueryError, "age"):
            self.ask("people", "3", "beauty")

    def test_console_npc_shows_the_age(self):
        alice = named(self.sim, "Alice")
        self.assertIn(f"age:       3/{alice.lifespan} cycles", console.fmt_npc(self.ask("npc", "Alice")))
        self.assertIn("age:       3/inf cycles", console.fmt_npc(self.ask("npc", "Maxima")))

    def test_console_people_table_has_an_age_column(self):
        header = console.fmt_people(self.ask("people")).splitlines()[1]
        self.assertEqual(["name", "age", "location"], header.split()[:3])

    def test_the_text_stays_plain_ascii(self):
        console.fmt_npc(self.ask("npc", "Maxima")).encode("ascii")
        console.fmt_people(self.ask("people")).encode("ascii")


if __name__ == "__main__":
    unittest.main()
