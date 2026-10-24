
import contextlib
import io
import itertools
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import console
import main
import person.person as person_module
import queries
import reproduction
from buildings import MegaBuilding
from persistence import save_state, load_state
from person import Person, GENDERS, DayTime
from person.maxima import Maxima
from person.person import FUTA_CHANCE, random_gender, CAN_CARRY, CAN_FATHER
from reproduction import pair_roles, pair_up
from services import TownHall
from simulation import Simulation

from townhelper import make_sim


def people(*genders):
    return [Person(name=f"{gender[0]}{number}", gender=gender) for number, gender in enumerate(genders)]


def town_with_room(places=50):
    town = TownHall("T")
    town.add_building(MegaBuilding("Homes", stories=places // 5, persons_per_unit=5, health=1, stamina=2, hunger=0, money=0))
    return town


class FakeRng:
    """a random number generator that says what it is told"""

    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value

    def choice(self, options):
        return options[0]


class TestGenders(unittest.TestCase):

    def test_the_genders(self):
        self.assertEqual(("male", "female", "futa"), GENDERS)
        self.assertEqual(("female", "futa"), CAN_CARRY)
        self.assertEqual(("male", "futa"), CAN_FATHER)

    def test_a_futa_is_one_in_a_million(self):
        self.assertEqual(1 / 1_000_000, FUTA_CHANCE)

    def test_the_chance_decides(self):
        self.assertEqual("futa", random_gender(FakeRng(FUTA_CHANCE / 2)))
        self.assertEqual("futa", random_gender(FakeRng(0.0)))
        self.assertEqual("male", random_gender(FakeRng(FUTA_CHANCE)))          # just not
        self.assertEqual("male", random_gender(FakeRng(0.5)))

    def test_without_a_futa_it_is_half_and_half(self):
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0):
            made = [Person().gender for _ in range(4000)]
        self.assertEqual({"male", "female"}, set(made))
        self.assertTrue(1800 <= made.count("male") <= 2200, made.count("male"))

    def test_a_chance_of_one_makes_everybody_a_futa(self):
        with mock.patch.object(person_module, "FUTA_CHANCE", 1.0):
            self.assertEqual({"futa"}, {Person().gender for _ in range(20)})

    def test_a_chosen_gender_stays(self):
        for gender in GENDERS:
            self.assertEqual(gender, Person(gender=gender).gender)

    def test_nonsense_genders(self):
        for bad in ("", "other", "Male", 1, "none"):
            with self.subTest(gender=bad), self.assertRaisesRegex(ValueError, "gender must be one of"):
                Person(gender=bad)

    def test_who_can_carry_and_who_can_father(self):
        self.assertEqual((False, True), (Person(gender="male").can_carry, Person(gender="male").can_father))
        self.assertEqual((True, False), (Person(gender="female").can_carry, Person(gender="female").can_father))
        self.assertEqual((True, True), (Person(gender="futa").can_carry, Person(gender="futa").can_father))

    def test_maxima_is_a_futa_whatever_the_chance(self):
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0):
            self.assertEqual("futa", Maxima().gender)
        self.assertEqual("futa", Maxima().gender)

    def test_having_parents_does_not_change_the_chance(self):
        # a futa is not passed on: a sim with parents is made like any other
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0):
            genders = {Person(parents=("Maxima", "x")).gender for _ in range(60)}
        self.assertEqual({"male", "female"}, genders)


class TestBecomingPregnant(unittest.TestCase):

    def test_who_can_carry(self):
        male, female, futa = people("male", "female", "futa")
        with self.assertRaisesRegex(ValueError, "a male cannot be pregnant"):
            male.become_pregnant(5, female)
        female.become_pregnant(5, male)
        futa.become_pregnant(5, male)
        self.assertIsNotNone(female.pregnancy)
        self.assertIsNotNone(futa.pregnancy)
        self.assertIsNone(male.pregnancy)

    def test_who_can_be_the_other_parent(self):
        male, female, futa = people("male", "female", "futa")
        with self.assertRaisesRegex(ValueError, "a female cannot be the other parent"):
            Person(gender="female").become_pregnant(5, female)
        Person(gender="futa").become_pregnant(5, futa)
        Person(gender="female").become_pregnant(5, futa)
        Person(gender="female").become_pregnant(5, male)

    def test_nothing_changes_when_it_does_not_work(self):
        male, female = people("male", "female")
        with self.assertRaises(ValueError):
            male.become_pregnant(5, female)
        self.assertIsNone(male.pregnancy)
        self.assertEqual(0, len(male.log))
        self.assertEqual(0, len(female.log))


class TestWhoIsTheMother(unittest.TestCase):

    def mothers(self, first_gender, second_gender, seeds=40):
        found = set()
        for seed in range(seeds):
            first, second = Person(gender=first_gender), Person(gender=second_gender)
            roles = pair_roles(first, second, random.Random(seed))
            found.add(None if roles is None else ("first" if roles[0] is first else "second"))
            if roles is not None:
                self.assertIn(roles[1], (first, second))
                self.assertIsNot(roles[0], roles[1])
        return found

    def test_two_males_or_two_females_cannot_have_a_baby(self):
        self.assertEqual({None}, self.mothers("male", "male"))
        self.assertEqual({None}, self.mothers("female", "female"))

    def test_the_female_carries_in_a_male_female_pair_either_way_round(self):
        self.assertEqual({"second"}, self.mothers("male", "female"))
        self.assertEqual({"first"}, self.mothers("female", "male"))

    def test_a_futa_carries_for_a_male(self):
        self.assertEqual({"first"}, self.mothers("futa", "male"))
        self.assertEqual({"second"}, self.mothers("male", "futa"))

    def test_a_futa_is_the_other_parent_of_a_female(self):
        self.assertEqual({"second"}, self.mothers("futa", "female"))
        self.assertEqual({"first"}, self.mothers("female", "futa"))

    def test_two_futas_flip_a_coin(self):
        self.assertEqual({"first", "second"}, self.mothers("futa", "futa"))

    def test_the_table_of_all_nine(self):
        expected = {
            ("male", "male"): None, ("female", "female"): None,
            ("male", "female"): "female", ("female", "male"): "female",
            ("futa", "male"): "futa", ("male", "futa"): "futa",
            ("futa", "female"): "female", ("female", "futa"): "female",
        }
        for first, second in itertools.product(GENDERS, GENDERS):
            roles = pair_roles(Person(gender=first), Person(gender=second), random.Random(1))
            if (first, second) in expected:
                self.assertEqual(expected[(first, second)], None if roles is None else roles[0].gender, (first, second))
            else:
                self.assertEqual("futa", roles[0].gender)        # futa + futa


class TestPairingUp(unittest.TestCase):

    def check(self, group, pairs):
        used = [id(p) for pair in pairs for p in pair]
        self.assertEqual(len(used), len(set(used)), "somebody is in two pairs")
        for first, second in pairs:
            self.assertIsNotNone(pair_roles(first, second), (first.gender, second.gender))

    def test_males_with_females(self):
        group = people("male", "male", "male", "female", "female", "female")
        pairs = pair_up(group, random.Random(1))
        self.assertEqual(3, len(pairs))
        self.check(group, pairs)
        self.assertTrue(all({a.gender, b.gender} == {"male", "female"} for a, b in pairs))

    def test_the_ones_without_a_partner_stay_alone(self):
        group = people("male", "male", "male", "male", "male", "female", "female")
        self.assertEqual(2, len(pair_up(group, random.Random(1))))

    def test_only_one_gender_means_no_pair(self):
        self.assertEqual([], pair_up(people("male", "male", "male"), random.Random(1)))
        self.assertEqual([], pair_up(people("female", "female"), random.Random(1)))
        self.assertEqual([], pair_up([], random.Random(1)))

    def test_a_futa_takes_the_one_who_is_left_over(self):
        for left_over in ("male", "female"):
            group = people("male", "female", left_over, "futa")
            pairs = pair_up(group, random.Random(1))
            self.assertEqual(2, len(pairs), left_over)
            futa_pair = next(pair for pair in pairs if any(p.gender == "futa" for p in pair))
            self.assertIn(left_over, [p.gender for p in futa_pair])

    def test_a_futa_stays_alone_when_everybody_else_is_paired(self):
        group = people("male", "male", "female", "female", "futa")
        pairs = pair_up(group, random.Random(1))
        self.assertEqual(2, len(pairs))
        self.assertTrue(all(p.gender != "futa" for pair in pairs for p in pair))

    def test_futas_pair_with_each_other_when_nobody_else_is_there(self):
        pairs = pair_up(people("futa", "futa", "futa"), random.Random(1))
        self.assertEqual(1, len(pairs))
        self.assertEqual([], pair_up(people("futa"), random.Random(1)))

    def test_a_futa_prefers_leftovers_to_another_futa(self):
        group = people("male", "futa", "futa")
        pairs = pair_up(group, random.Random(1))
        self.assertEqual(1, len(pairs))
        self.assertIn("male", [p.gender for p in pairs[0]])

    def test_no_pair_that_could_still_be_made_is_left(self):
        for seed in range(300):
            rng = random.Random(seed)
            group = [Person(name=f"p{n}", gender=rng.choice(("male", "female", "female", "futa", "male", "male")))
                     for n in range(rng.randint(0, 14))]
            pairs = pair_up(group, rng)
            self.check(group, pairs)

            paired = {id(p) for pair in pairs for p in pair}
            lonely = [p for p in group if id(p) not in paired]
            for first, second in itertools.combinations(lonely, 2):
                self.assertIsNone(pair_roles(first, second),
                                  f"seed {seed}: {first.gender} and {second.gender} were left but could have a baby")

    def test_the_group_is_not_changed(self):
        group = people("male", "female", "futa")
        names = [p.name for p in group]
        pair_up(group, random.Random(1))
        self.assertEqual(names, [p.name for p in group])

    def test_the_same_random_numbers_give_the_same_pairs(self):
        group = people("male", "male", "female", "female", "futa", "male")
        first = [(a.name, b.name) for a, b in pair_up(group, random.Random(7))]
        second = [(a.name, b.name) for a, b in pair_up(group, random.Random(7))]
        self.assertEqual(first, second)


class TestMeetingByGender(unittest.TestCase):

    def meet(self, *genders):
        town = town_with_room()
        persons = []
        for number, gender in enumerate(genders):
            person = Person(name=f"{gender[0]}{number}", gender=gender, age=25)
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            person.go(town.home_buildings[0].get_unit(0))        # all in the same place
            persons.append(person)
        with mock.patch.object(reproduction, "MATE_CHANCE", 1.0):
            return reproduction.meet(persons, DayTime.EVENING)

    def test_two_males_or_two_females_never_meet_for_a_baby(self):
        self.assertEqual([], self.meet("male", "male"))
        self.assertEqual([], self.meet("female", "female"))

    def test_every_other_pair_does(self):
        for first, second in (("male", "female"), ("female", "male"), ("futa", "male"), ("female", "futa"), ("futa", "futa")):
            with self.subTest(first=first, second=second):
                self.assertEqual(1, len(self.meet(first, second)))

    def test_three_males_and_a_female_make_one_couple(self):
        self.assertEqual(1, len(self.meet("male", "male", "male", "female")))


class TestConceivingByGender(unittest.TestCase):

    def setUp(self):
        self.town = town_with_room(60)

    def sim(self, gender):
        person = Person(name=f"{gender}-{id(object())}", gender=gender, age=25)
        self.town.add_citizen(person)
        return person

    def conceive(self, first, second, seed=1):
        return reproduction.conceive(self.town, [(first, second, DayTime.EVENING)], 3, random.Random(seed))

    def test_the_female_is_the_mother_of_a_male_female_pair(self):
        male, female = self.sim("male"), self.sim("female")
        self.assertEqual(1, self.conceive(male, female))
        self.assertIsNone(male.pregnancy)
        self.assertEqual((5, male), tuple(female.pregnancy))

    def test_a_futa_carries_the_baby_of_a_male(self):
        male, futa = self.sim("male"), self.sim("futa")
        self.assertEqual(1, self.conceive(futa, male))
        self.assertIsNone(male.pregnancy)
        self.assertEqual(male, futa.pregnancy.partner)

    def test_a_futa_is_the_other_parent_of_a_female(self):
        female, futa = self.sim("female"), self.sim("futa")
        self.assertEqual(1, self.conceive(futa, female))
        self.assertIsNone(futa.pregnancy)
        self.assertEqual(futa, female.pregnancy.partner)

    def test_two_futas_can_both_end_up_as_the_mother(self):
        mothers = set()
        for seed in range(30):
            first, second = self.sim("futa"), self.sim("futa")
            self.conceive(first, second, seed)
            mothers.add("first" if first.pregnancy else "second")
        self.assertEqual({"first", "second"}, mothers)

    def test_a_couple_that_cannot_have_a_baby_is_skipped_and_uses_no_place(self):
        self.town = town_with_room(5)
        for number in range(4):                  # leaves exactly one free place
            filler = self.sim("male")
            filler.find_place_to_live(self.town.list_of_buildings())
        self.assertEqual(1, self.town.free_home_places())

        two_males = (self.sim("male"), self.sim("male"), None)
        a_couple = (self.sim("male"), self.sim("female"), None)
        for seed in range(10):
            self.assertEqual(1, reproduction.conceive(self.town, [two_males, a_couple], 1, random.Random(seed)))
            a_couple[1].pregnancy = None

    def test_maxima_carries_for_males_and_fathers_for_females(self):
        for seed in range(20):
            maxima = Maxima()
            self.town.add_citizen(maxima)
            male, female = self.sim("male"), self.sim("female")

            self.conceive(maxima, male, seed)
            self.assertIsNotNone(maxima.pregnancy)
            maxima.pregnancy = None

            self.conceive(maxima, female, seed)
            self.assertIsNone(maxima.pregnancy)
            self.assertEqual(maxima, female.pregnancy.partner)

    def test_the_other_parent_counts_the_child_too(self):
        female, futa = self.sim("female"), self.sim("futa")
        self.conceive(female, futa)
        reproduction.give_births(self.town, 5)
        self.assertEqual((1, 1), (female.children, futa.children))


class TestTheBabies(unittest.TestCase):

    def test_babies_are_male_or_female_by_chance(self):
        town = town_with_room(400)
        mothers = []
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0):
            for number in range(150):
                mother = Person(name=f"m{number}", gender="female", age=25)
                father = Person(name=f"f{number}", gender="male", age=25)
                town.add_citizen(mother)
                mother.become_pregnant(2, father)
                mothers.append(mother)

            babies = reproduction.give_births(town, 2)

        genders = [baby.gender for baby in babies]
        self.assertEqual(150, len(babies))
        self.assertEqual({"male", "female"}, set(genders))
        self.assertTrue(50 <= genders.count("male") <= 100, genders.count("male"))

    def test_a_baby_of_maxima_is_no_futa_and_no_maxima(self):
        town = town_with_room(100)
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0):
            for number in range(30):
                maxima = Maxima()
                town.add_citizen(maxima)
                maxima.become_pregnant(2, Person(name=f"d{number}", gender="male"))
                (baby,) = [b for b in reproduction.give_births(town, 2)]
                self.assertIn(baby.gender, ("male", "female"))
                self.assertNotEqual(float("inf"), baby.lifespan)
                self.assertNotEqual(float("inf"), baby.fertile_ages[1])


class TestInTheSimulation(unittest.TestCase):

    def run_pair(self, first_gender, second_gender, cycles=8):
        town = TownHall("T")
        town.add_building(MegaBuilding("Homes", stories=4, persons_per_unit=4, health=1, stamina=2, hunger=0, money=0))
        for name, gender in (("One", first_gender), ("Two", second_gender)):
            person = Person(name=name, age=25, routine=1, gender=gender)
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
        sim = Simulation(town)
        with mock.patch.object(reproduction, "MATE_CHANCE", 1.0):
            sim.run(cycles)
        return len(sim.living())

    def test_two_males_or_two_females_never_get_a_baby_however_often_they_meet(self):
        self.assertEqual(2, self.run_pair("male", "male"))
        self.assertEqual(2, self.run_pair("female", "female"))

    def test_the_others_do(self):
        for first, second in (("male", "female"), ("futa", "male"), ("female", "futa"), ("futa", "futa")):
            with self.subTest(first=first, second=second):
                self.assertGreater(self.run_pair(first, second), 2)


class TestShowingTheGender(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_npc(self):
        self.assertEqual("futa", self.ask("npc", "Maxima")["gender"])
        self.assertIn(self.ask("npc", "Alice")["gender"], GENDERS)

    def test_people(self):
        people = self.ask("people", "10")["people"]
        self.assertTrue(all(p["gender"] in GENDERS for p in people))
        self.assertEqual("futa", next(p for p in people if p["name"] == "Maxima")["gender"])

    def test_world_counts_the_genders(self):
        genders = self.ask("world")["population"]["genders"]
        self.assertEqual(set(GENDERS), set(genders))
        self.assertEqual(5, sum(genders.values()))
        self.assertGreaterEqual(genders["futa"], 1)

    def test_the_text_for_an_npc(self):
        self.assertIn("gender:    futa", console.fmt_npc(self.ask("npc", "Maxima")))

    def test_the_people_table_has_a_gender_column(self):
        text = console.fmt_people(self.ask("people"))
        self.assertEqual(["name", "age", "gender", "location"], text.splitlines()[1].split()[:4])
        self.assertIn("futa", text)

    def test_the_text_for_the_world(self):
        line = next(l for l in console.fmt_world(self.ask("world")).splitlines() if l.strip().startswith("genders:"))
        self.assertRegex(line, r"genders:\s+\d+ male, \d+ female, \d+ futa")

    def test_everything_can_be_sent_as_json(self):
        import json
        for cmd, args in (("npc", ["Maxima"]), ("people", []), ("world", []), ("snapshot", ["Maxima"])):
            with self.subTest(cmd=cmd):
                json.dumps(queries.run(self.sim, cmd, args))

    def test_plain_ascii(self):
        console.fmt_npc(self.ask("npc", "Maxima")).encode("ascii")
        console.fmt_people(self.ask("people")).encode("ascii")
        console.fmt_world(self.ask("world")).encode("ascii")

    def test_the_gender_survives_saving(self):
        before = {p.name: p.gender for p in self.sim.town_hall.citizens}
        with tempfile.TemporaryDirectory() as tmp:
            save_state(self.sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")
        self.assertEqual(before, {p.name: p.gender for p in loaded.town_hall.citizens})


class TestTheDemoTown(unittest.TestCase):

    def test_maxima_is_the_futa_and_the_rest_are_males_and_females(self):
        with mock.patch.object(person_module, "FUTA_CHANCE", 0.0), contextlib.redirect_stdout(io.StringIO()):
            town = main.build_town()
        counts = {gender: sum(1 for p in town.citizens if p.gender == gender) for gender in GENDERS}

        self.assertEqual(1, counts["futa"])
        self.assertEqual("futa", next(p for p in town.citizens if p.name == "Maxima").gender)
        self.assertTrue(440 <= counts["male"] <= 560, counts)
        self.assertEqual(1002, sum(counts.values()))


if __name__ == "__main__":
    unittest.main()
