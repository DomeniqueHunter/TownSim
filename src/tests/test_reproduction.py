
import contextlib
import io
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import console
import main
import queries
import reproduction
from buildings import MegaBuilding, Mansion, WorkBuilding, Shop
from persistence import save_state, load_state
from person import Person, ADULT_AGE, FERTILE_AGES
from person.person import Pregnancy
from services import TownHall
from simulation import Simulation


def make_town(unit_size=4, units=1, spare_places=0, jobs=10):
    """a town with free homes (rent 0), a job place and a shop, but nobody in it yet"""
    town = TownHall("Familyville")
    town.add_building(MegaBuilding("Home", stories=units, persons_per_unit=unit_size,
                                   health=1, stamina=2, hunger=0, money=0))
    if spare_places:
        # clearly the worst home, so sims only move in when the normal home is full
        town.add_building(MegaBuilding("Spare", stories=1, persons_per_unit=spare_places,
                                       health=0, stamina=0, hunger=-1, money=0))
    town.add_building(WorkBuilding("Job", work_places=jobs))
    town.add_building(Shop("Shop", work_places=5))
    return town


def add(town, name, age=25, routine=1, grown_up_life=True):
    """a sim that lives in the town (and works and shops if it is a grown up)"""
    person = Person(name=name, age=age, routine=routine)
    town.add_citizen(person)
    person.find_place_to_live(town.list_of_buildings())
    if grown_up_life and person.is_adult:
        town.integrate_adult(person)
    person.go(person.home)
    return person


def always_mate():
    return mock.patch.object(reproduction, "MATE_CHANCE", 1.0)


def never_mate():
    return mock.patch.object(reproduction, "MATE_CHANCE", 0.0)


class TestPersonRules(unittest.TestCase):

    def test_adult_age(self):
        self.assertEqual(18, ADULT_AGE)
        self.assertFalse(Person(age=17).is_adult)
        self.assertTrue(Person(age=18).is_adult)
        self.assertTrue(Person().is_adult)

    def test_who_can_mate(self):
        low, high = FERTILE_AGES
        self.assertFalse(Person(age=low - 1).can_mate())
        self.assertTrue(Person(age=low).can_mate())
        self.assertTrue(Person(age=high).can_mate())
        self.assertFalse(Person(age=high + 1).can_mate())

    def test_a_pregnant_sim_cannot_mate_again(self):
        mother, other = Person(), Person()
        mother.become_pregnant(5, other)
        self.assertFalse(mother.can_mate())
        self.assertTrue(other.can_mate())

    def test_the_dead_cannot_mate(self):
        person = Person()
        person.die()
        self.assertFalse(person.can_mate())

    def test_pregnancy_is_remembered_and_noted_for_both(self):
        mother, other = Person(name="Ann"), Person(name="Bob")
        mother.become_pregnant(5, other)

        self.assertEqual(Pregnancy(5, other), mother.pregnancy)
        self.assertIn("pregnant with the child of Bob, due in cycle 5", mother.log[-1][2])
        self.assertIn("Ann is expecting their child, due in cycle 5", other.log[-1][2])

    def test_a_mother_who_dies_loses_the_baby(self):
        mother = Person()
        mother.become_pregnant(5, Person())
        mother.die("old age")
        self.assertIsNone(mother.pregnancy)

    def test_family_defaults(self):
        person = Person()
        self.assertEqual((None, 0, None), (person.parents, person.children, person.pregnancy))
        self.assertEqual(("A", "B"), Person(parents=("A", "B")).parents)


class TestMeeting(unittest.TestCase):

    def setUp(self):
        self.town = make_town(unit_size=4, units=2, spare_places=1)
        self.ann = add(self.town, "Ann")
        self.bob = add(self.town, "Bob")
        self.unit = self.ann.home

    def meet(self, people, cycle=1, rng=random):
        return reproduction.meet(self.town, people, cycle, None, rng)

    def test_two_sims_who_relax_together_can_mate(self):
        with always_mate():
            self.assertEqual(1, self.meet([self.ann, self.bob]))

        pregnant = [p for p in (self.ann, self.bob) if p.pregnancy]
        self.assertEqual(1, len(pregnant))
        mother = pregnant[0]
        other = self.bob if mother is self.ann else self.ann
        self.assertEqual(Pregnancy(1 + reproduction.PREGNANCY_CYCLES, other), mother.pregnancy)
        self.assertIsNone(other.pregnancy)

    def test_the_baby_is_due_two_cycles_later(self):
        self.assertEqual(2, reproduction.PREGNANCY_CYCLES)
        with always_mate():
            self.meet([self.ann, self.bob], cycle=7)
        due = (self.ann.pregnancy or self.bob.pregnancy).due_cycle
        self.assertEqual(9, due)

    def test_the_mother_is_chosen_by_chance(self):
        mothers = set()
        for seed in range(40):
            ann, bob = add(make_town(), "Ann"), add(make_town(), "Bob")
            ann.go(self.unit), bob.go(self.unit)
            with always_mate():
                reproduction.meet(self.town, [ann, bob], 1, None, random.Random(seed))
            mothers.add("Ann" if ann.pregnancy else "Bob")
        self.assertEqual({"Ann", "Bob"}, mothers)

    def test_no_chance_no_baby(self):
        with never_mate():
            self.assertEqual(0, self.meet([self.ann, self.bob]))
        self.assertIsNone(self.ann.pregnancy or self.bob.pregnancy)

    def test_sims_in_different_places_do_not_meet(self):
        carl = add(self.town, "Carl")
        carl.go(self.town.home_buildings[0].get_unit(1))
        with always_mate():
            self.assertEqual(0, self.meet([self.ann, carl]))

    def test_children_and_old_sims_do_not_mate(self):
        child = add(self.town, "Child", age=10)
        elder = add(self.town, "Elder", age=FERTILE_AGES[1] + 1)
        with always_mate():
            self.assertEqual(0, self.meet([child, elder]))
            self.assertEqual(0, self.meet([child, self.ann]))

    def test_pregnant_sims_do_not_mate_again(self):
        self.ann.become_pregnant(9, self.bob)
        with always_mate():
            self.assertEqual(0, self.meet([self.ann, self.bob]))

    def test_an_odd_one_out_stays_alone(self):
        carl = add(self.town, "Carl")
        with always_mate():
            self.assertEqual(1, self.meet([self.ann, self.bob, carl]))

    def test_every_place_has_its_own_couples(self):
        carl, dora = add(self.town, "Carl"), add(self.town, "Dora")
        other_unit = self.town.home_buildings[0].get_unit(1)
        carl.go(other_unit), dora.go(other_unit)
        # the town must have room for two babies
        self.town.add_building(MegaBuilding("More", stories=1, persons_per_unit=5, health=1, stamina=2, hunger=0, money=0))
        with always_mate():
            self.assertEqual(2, self.meet([self.ann, self.bob, carl, dora]))

    def test_sims_that_are_nowhere_do_not_meet(self):
        nowhere1, nowhere2 = Person(), Person()
        with always_mate():
            self.assertEqual(0, self.meet([nowhere1, nowhere2]))

    def test_no_baby_without_a_place_to_live(self):
        town = make_town(unit_size=2, units=1)         # the two sims fill the only home
        ann, bob = add(town, "Ann"), add(town, "Bob")
        self.assertEqual(0, town.free_home_places())

        with always_mate():
            self.assertEqual(0, reproduction.meet(town, [ann, bob], 1))

    def test_every_baby_on_its_way_needs_a_place(self):
        town = make_town(unit_size=2, units=3, spare_places=1)        # 3 couples and room for ONE baby
        people = [add(town, f"P{i}") for i in range(6)]
        with always_mate():
            self.assertEqual(1, reproduction.meet(town, people, 1))

        # and the place stays reserved until the baby is born
        with always_mate():
            self.assertEqual(0, reproduction.meet(town, [p for p in people if p.pregnancy is None], 1))
        self.assertEqual(1, reproduction.pregnant_count(town))


class TestPlacesAndJobs(unittest.TestCase):

    def test_free_places_are_only_the_free_homes_with_room(self):
        town = make_town(unit_size=3, units=2)
        self.assertEqual(6, town.free_home_places())
        add(town, "Ann")
        self.assertEqual(5, town.free_home_places())

        town.add_building(Mansion("Villa"))             # costs rent, not for sims without money
        self.assertEqual(5, town.free_home_places())

    def test_a_baby_lives_with_its_mother_if_there_is_room(self):
        town = make_town(unit_size=3)
        mother = add(town, "Mother")
        baby = Person(age=0)
        town.add_citizen(baby)

        self.assertTrue(town.place_newborn(baby, mother))
        self.assertIs(mother.home, baby.home)
        self.assertIn(baby, mother.home.owners)

    def test_a_baby_goes_elsewhere_when_her_unit_is_full(self):
        town = make_town(unit_size=2, units=2)
        mother, other = add(town, "Mother"), add(town, "Other")
        self.assertIs(mother.home, other.home)
        baby = Person(age=0)
        town.add_citizen(baby)

        self.assertTrue(town.place_newborn(baby, mother))
        self.assertIsNot(mother.home, baby.home)
        self.assertIn(baby, baby.home.owners)

    def test_no_place_at_all(self):
        town = make_town(unit_size=1, units=1)
        mother = add(town, "Mother")
        baby = Person(age=0)
        town.add_citizen(baby)

        self.assertFalse(town.place_newborn(baby, mother))
        self.assertIsNone(baby.home)

    def test_a_grown_up_gets_a_shop_and_the_first_free_job(self):
        town = make_town(jobs=1)
        first = add(town, "First", grown_up_life=False)
        second = add(town, "Second", grown_up_life=False)

        town.integrate_adult(first)
        town.integrate_adult(second)

        self.assertEqual(town.shop_buildings[0], first.shop)
        self.assertEqual("Job", first.workplace.name)
        self.assertEqual("Shop", second.workplace.name)      # the Job has only one place, the shop is next

    def test_no_job_left(self):
        town = TownHall("T")
        town.add_building(MegaBuilding("Home", stories=1, persons_per_unit=2, money=0))
        person = add(town, "Jobless")
        town.integrate_adult(person)
        self.assertIsNone(person.workplace)


class TestBirths(unittest.TestCase):

    def setUp(self):
        self.town = make_town(unit_size=4, units=2)
        self.mother = add(self.town, "Ann")
        self.other = add(self.town, "Bob")
        self.mother.become_pregnant(3, self.other)

    def births(self, cycle):
        return reproduction.give_births(self.town, cycle)

    def test_the_baby_is_born_when_it_is_due(self):
        self.assertEqual([], self.births(2))
        (baby,) = self.births(3)

        self.assertEqual(0, baby.age)
        self.assertFalse(baby.is_adult)
        self.assertTrue(90 <= baby.lifespan <= 110)
        self.assertEqual(("Ann", "Bob"), baby.parents)
        self.assertIn(baby, self.town.citizens)
        self.assertIs(self.town.ledger, baby.ledger)
        self.assertIn(baby, self.town.newcomers)

    def test_the_baby_lives_with_the_mother(self):
        (baby,) = self.births(3)
        self.assertIs(self.mother.home, baby.home)

    def test_the_parents_are_updated(self):
        self.births(3)
        self.assertIsNone(self.mother.pregnancy)
        self.assertEqual(1, self.mother.children)
        self.assertEqual(1, self.other.children)
        self.assertTrue(self.mother.can_mate())

    def test_a_late_baby_is_still_born(self):
        self.assertEqual(1, len(self.births(7)))

    def test_nobody_is_born_twice(self):
        self.births(3)
        self.assertEqual([], self.births(3))

    def test_a_dead_mother_loses_the_baby(self):
        self.mother.die("old age")
        self.assertEqual([], self.births(3))
        self.assertEqual(0, self.other.children)

    def test_the_other_parent_may_be_dead(self):
        self.other.die("old age")
        (baby,) = self.births(3)

        self.assertEqual(("Ann", "Bob"), baby.parents)
        self.assertEqual(1, self.mother.children)
        self.assertEqual(0, self.other.children)

    def test_everybody_gets_a_note(self):
        (baby,) = self.births(3)
        short = baby.name[:8]
        self.assertEqual(f"gave birth to {short}", self.mother.log[-1][2])
        self.assertEqual(f"Ann gave birth to their child {short}", self.other.log[-1][2])
        self.assertEqual("born to Ann and Bob", baby.log[-1][2])

    def test_twins_do_not_happen_but_two_mothers_can_give_birth_in_the_same_cycle(self):
        carl, dora = add(self.town, "Carl"), add(self.town, "Dora")
        carl.become_pregnant(3, dora)
        self.assertEqual(2, len(self.births(3)))

    def test_a_baby_without_a_home_is_still_born(self):
        town = make_town(unit_size=1, units=1)
        mother, other = add(town, "Ann"), Person(name="Bob")
        mother.become_pregnant(3, other)

        (baby,) = reproduction.give_births(town, 3)
        self.assertIsNone(baby.home)


class TestChildren(unittest.TestCase):

    def test_children_get_no_hungry_and_need_no_food(self):
        town = make_town()
        child = add(town, "Child", age=5)
        sim = Simulation(town)

        sim.run(8)

        self.assertTrue(child.alive)
        self.assertEqual(0, child.attributes.hunger)
        self.assertEqual(0, child.inventory["food"])

    def test_children_stay_at_home_all_day(self):
        town = make_town()
        child = add(town, "Child", age=5)
        sim = Simulation(town)

        for _ in range(10):
            sim.step()
            self.assertIs(child.home, child.current_location)
        self.assertIsNone(child.workplace)
        self.assertIsNone(child.shop)
        self.assertEqual(0, child.money())

    def test_coming_of_age_brings_shop_and_job(self):
        town = make_town()
        teen = add(town, "Teen", age=ADULT_AGE - 1)
        sim = Simulation(town)
        self.assertIsNone(teen.workplace)

        sim.run(1)

        self.assertTrue(teen.is_adult)
        self.assertEqual("Job", teen.workplace.name)
        self.assertIsNotNone(teen.shop)

        sim.run(3)
        self.assertGreater(teen.totals["money_earned"], 0)
        self.assertTrue(teen.alive)

    def test_coming_of_age_happens_once(self):
        town = make_town()
        teen = add(town, "Teen", age=ADULT_AGE - 1)
        sim = Simulation(town)
        sim.run(5)
        self.assertEqual(1, teen.workplace.employees.count(teen))

    def test_a_grown_up_without_a_job_starves_after_ten_days(self):
        town = TownHall("T")
        town.add_building(MegaBuilding("Home", stories=1, persons_per_unit=2, health=1, stamina=2, money=0))
        teen = add(town, "Teen", age=ADULT_AGE - 1)
        sim = Simulation(town)

        sim.run(10)            # cycle 1: grows up, cycles 2..10: hunger 1..9
        self.assertTrue(teen.alive)
        sim.run(1)
        self.assertFalse(teen.alive)
        self.assertEqual("starvation", teen.cause_of_death)

    def test_children_do_not_meet_each_other(self):
        town = make_town()
        add(town, "A", age=10), add(town, "B", age=11)
        sim = Simulation(town)
        with always_mate():
            sim.run(5)
        self.assertEqual(0, reproduction.pregnant_count(town))


class TestFullSequence(unittest.TestCase):
    """two sims in one home: mating, pregnancy, birth, growing up - through the simulation"""

    def setUp(self):
        self.town = make_town(unit_size=4)
        self.ann = add(self.town, "Ann")
        self.bob = add(self.town, "Bob")
        self.sim = Simulation(self.town)

    def test_the_baby_comes_two_cycles_after_the_mating(self):
        with always_mate():
            self.sim.run(1)
            mother = self.ann if self.ann.pregnancy else self.bob
            self.assertEqual(3, mother.pregnancy.due_cycle)
            self.assertEqual({"cycle": 1, "died": 0, "new": 0}, self.sim.last_cycle())

            self.sim.run(1)
            self.assertEqual(2, len(self.sim.living()))
            self.assertEqual(0, self.sim.last_cycle()["new"])

            self.sim.run(1)
            self.assertEqual(3, len(self.sim.living()))
            self.assertEqual({"cycle": 3, "died": 0, "new": 1}, self.sim.last_cycle())

        baby = next(p for p in self.sim.living() if p.parents)
        self.assertEqual(0, baby.age)
        self.assertEqual(sorted(["Ann", "Bob"]), sorted(baby.parents))
        self.assertIs(mother.home, baby.home)

    def test_the_log_line_shows_the_baby_in_that_cycle_only(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out), always_mate():
            main.run_cycles(self.sim, 4, Path(tmp) / "save.pkl")

        lines = out.getvalue().splitlines()
        self.assertIn("alive 2, died 0, new 0,", lines[0])
        self.assertIn("alive 2, died 0, new 0,", lines[1])
        self.assertIn("alive 3, died 0, new 1,", lines[2])
        self.assertIn("alive 3, died 0, new 0,", lines[3])

    def test_the_baby_grows_up_and_gets_a_job(self):
        with always_mate():
            self.sim.run(3)
        baby = next(p for p in self.sim.living() if p.parents)

        with never_mate():
            self.sim.run(ADULT_AGE - 1)
            self.assertFalse(baby.is_adult)
            self.assertIsNone(baby.workplace)
            self.assertEqual(0, baby.attributes.hunger)

            self.sim.run(1)
        self.assertTrue(baby.is_adult)
        self.assertIsNotNone(baby.workplace)
        self.assertIsNotNone(baby.shop)

    def test_nothing_happens_without_a_free_place(self):
        town = make_town(unit_size=2)           # only room for the two of them
        add(town, "Ann"), add(town, "Bob")
        sim = Simulation(town)
        with always_mate():
            sim.run(10)
        self.assertEqual(2, len(sim.living()))

    def test_lonely_sims_have_no_children(self):
        town = make_town(unit_size=1, units=2)
        add(town, "Ann"), add(town, "Bob")      # each lives alone
        sim = Simulation(town)
        with always_mate():
            sim.run(10)
        self.assertEqual(2, len(sim.living()))


class TestGrowingTown(unittest.TestCase):
    """the population must not die out and must stay inside what homes and jobs allow"""

    def run_town(self, seed, founders=100, capacity=200, cycles=250):
        random.seed(seed)
        town = TownHall("Growville")
        town.add_building(MegaBuilding("Homes", stories=capacity // 10, persons_per_unit=10,
                                       health=1, stamina=2, hunger=0, money=0))
        town.add_building(WorkBuilding("Factory", work_places=capacity))
        town.add_building(Shop("Shop", work_places=capacity))
        for _ in range(founders):
            person = Person(age=random.randint(0, 89))
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            if person.is_adult:
                town.integrate_adult(person)
        sim = Simulation(town)

        alive, births = [], 0
        for _ in range(cycles):
            sim.run_cycle()
            alive.append(len(sim.living()))
            births += sim.last_cycle()["new"]
        return sim, alive, births

    def test_the_town_survives_for_many_generations(self):
        for seed in (11, 12):
            with self.subTest(seed=seed):
                sim, alive, births = self.run_town(seed)

                self.assertGreater(min(alive), 0, "the town died out")
                self.assertLessEqual(max(alive), 200, "more sims than places to live")
                self.assertGreater(births, 100)
                self.assertGreater(alive[-1], 60)

                causes = {}
                for grave in sim.town_hall.graveyard:
                    causes[grave.cause] = causes.get(grave.cause, 0) + 1
                self.assertGreater(causes.get("old age", 0), 100)
                self.assertLess(causes.get("starvation", 0), 20)       # jobs are not the limit here

    def test_everybody_has_a_home(self):
        sim, _, _ = self.run_town(13, cycles=150)
        self.assertTrue(all(p.home is not None for p in sim.living()))


class TestQueriesAndConsole(unittest.TestCase):

    def setUp(self):
        self.town = make_town(unit_size=4)
        self.ann = add(self.town, "Ann")
        self.bob = add(self.town, "Bob")
        self.child = add(self.town, "Kid", age=3)
        self.sim = Simulation(self.town)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_a_pregnant_sim(self):
        self.ann.become_pregnant(5, self.bob)
        data = self.ask("npc", "Ann")

        self.assertEqual({"due_cycle": 5, "partner": "Bob"}, data["pregnancy"])
        self.assertTrue(data["adult"])
        self.assertIsNone(data["parents"])
        self.assertEqual(0, data["children"])
        self.assertIsNone(self.ask("npc", "Bob")["pregnancy"])

    def test_a_child_and_its_parents(self):
        kid = Person(age=0, parents=("Ann", "Bob"), name="Baby")
        self.town.add_citizen(kid)
        self.ann.children = 1
        data = self.ask("npc", "Baby")

        self.assertFalse(data["adult"])
        self.assertEqual(["Ann", "Bob"], data["parents"])
        self.assertEqual(1, self.ask("npc", "Ann")["children"])

    def test_world_counts_children_and_pregnancies(self):
        self.ann.become_pregnant(5, self.bob)
        population = self.ask("world")["population"]

        self.assertEqual(3, population["alive"])
        self.assertEqual(1, population["children"])
        self.assertEqual(1, population["pregnant"])

    def test_console_npc_family_lines(self):
        self.ann.become_pregnant(5, self.bob)
        self.ann.children = 2
        text = console.fmt_npc(self.ask("npc", "Ann"))

        self.assertIn("family:    founder, no parents in town, 2 children", text)
        self.assertIn("pregnant:  baby due in cycle 5 (with Bob)", text)
        self.assertNotIn("pregnant:", console.fmt_npc(self.ask("npc", "Bob")))

    def test_console_shows_parents_and_child(self):
        kid = Person(age=0, parents=("Ann", "Bob"), name="Baby")
        self.town.add_citizen(kid)
        text = console.fmt_npc(self.ask("npc", "Baby"))

        self.assertIn("family:    parents Ann and Bob, 0 children", text)
        self.assertIn("0/", text.split("age:")[1].split("\n")[0].replace(" ", ""))
        self.assertIn("cycles, child", text)
        self.assertIn("cycles, adult", console.fmt_npc(self.ask("npc", "Ann")))

    def text_when(self, name, action_type):
        """steps the town until the sim does this action, returns what the console says about it"""
        for _ in range(30):
            where = self.ask("where", name)["action"]
            if where["type"] == action_type:
                return where["text"]
            self.sim.step()
        self.fail(f"{name} never did {action_type}")

    def test_a_child_is_too_young_for_work_and_shop_but_not_for_leisure(self):
        self.assertEqual("working (too young, stays home)", self.text_when("Kid", "WORK"))
        self.assertEqual("shopping (too young, stays home)", self.text_when("Kid", "SHOP"))
        # there are no leisure places for anybody yet, that has nothing to do with age
        self.assertIn("no leisure place", self.text_when("Kid", "LEISURE"))

    def test_a_grown_up_without_a_job_is_told_differently(self):
        add(self.town, "Jobless", grown_up_life=False)
        self.assertEqual("working (has no workplace, stays home)", self.text_when("Jobless", "WORK"))

    def test_console_world_line(self):
        self.ann.become_pregnant(5, self.bob)
        self.assertIn("children:   1 not grown up yet, 1 pregnant", console.fmt_world(self.ask("world")))

    def test_the_text_stays_plain_ascii(self):
        self.ann.become_pregnant(5, self.bob)
        console.fmt_npc(self.ask("npc", "Ann")).encode("ascii")
        console.fmt_world(self.ask("world")).encode("ascii")


class TestSaving(unittest.TestCase):

    def test_pregnancy_and_family_survive_saving(self):
        town = make_town(unit_size=4)
        ann, bob = add(town, "Ann"), add(town, "Bob")
        sim = Simulation(town)
        with always_mate():
            sim.run(1)
        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        people = {p.name: p for p in loaded.town_hall.citizens}
        mother = people["Ann"] if people["Ann"].pregnancy else people["Bob"]
        other = people["Bob"] if mother is people["Ann"] else people["Ann"]
        self.assertEqual(3, mother.pregnancy.due_cycle)
        self.assertIs(other, mother.pregnancy.partner)          # still the same object, not a copy

        with always_mate():
            loaded.run(2)
        self.assertEqual(3, len(loaded.living()))
        baby = next(p for p in loaded.living() if p.parents)
        self.assertEqual(sorted(["Ann", "Bob"]), sorted(baby.parents))


if __name__ == "__main__":
    unittest.main()
