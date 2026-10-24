
import contextlib
import io
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import console
import display
import main
import queries
import reproduction
from buildings import Brothel, MegaBuilding, Shop, WorkBuilding, WAGES
from persistence import save_state, load_state
from person import Person, ADULT_AGE, ActionType, DayTime
from person.maxima import Maxima
from services import TownHall
from simulation import Simulation
from stats import Stats


def make_club(price=10, work_places=5, boss_age=40, spare=0):
    """a town with homes and a brothel, whose boss lives there. Returns (town, club, boss)"""
    town = TownHall("Clubtown")
    town.add_building(MegaBuilding("Homes", stories=6, persons_per_unit=4, health=1, stamina=2, hunger=0, money=0))
    if spare:
        town.add_building(MegaBuilding("Spare", stories=1, persons_per_unit=spare, health=0, stamina=0, hunger=-1, money=0))
    boss = Person(name="Boss", age=boss_age, routine=1)
    town.add_citizen(boss)
    boss.find_place_to_live(town.list_of_buildings())
    club = Brothel("Club", boss=boss, work_places=work_places, price=price)
    town.add_building(club)
    boss.find_leisure_spot(town.leisure_buildings)
    return town, club, boss


def guest(town, name, money=100, routine=1, age=30, own_unit=False):
    """a grown up (no job) who can relax at the leisure place"""
    person = Person(name=name, age=age, routine=routine)
    person.attributes += Stats(money=money)
    town.add_citizen(person)
    person.find_place_to_live(town.list_of_buildings())
    person.find_leisure_spot(town.leisure_buildings)
    return person


def always_mate():
    return mock.patch.object(reproduction, "MATE_CHANCE", 1.0)


class TestTheBuilding(unittest.TestCase):

    def test_it_needs_a_boss(self):
        with self.assertRaisesRegex(ValueError, "needs a boss"):
            Brothel("Club")

    def test_the_boss_has_to_be_a_living_grown_up(self):
        with self.assertRaisesRegex(ValueError, "living grown up"):
            Brothel("Club", boss=Person(age=ADULT_AGE - 1))
        dead = Person()
        dead.die()
        with self.assertRaisesRegex(ValueError, "living grown up"):
            Brothel("Club", boss=dead)

    def test_the_boss_cannot_have_another_job(self):
        factory = WorkBuilding("Factory")
        boss = Person()
        factory.employ(boss)
        with self.assertRaisesRegex(ValueError, "already works somewhere else"):
            Brothel("Club", boss=boss)

    def test_nonsense_settings(self):
        boss = Person()
        with self.assertRaises(ValueError):
            Brothel("Club", boss=boss, work_places=0)
        with self.assertRaises(ValueError):
            Brothel("Club", boss=boss, price=-1)
        with self.assertRaisesRegex(ValueError, "health and stamina"):
            Brothel("Club", boss=boss, effects={"hunger": -3})

    def test_the_boss_works_there(self):
        town, club, boss = make_club()

        self.assertIs(club, boss.workplace)
        self.assertIn(boss, club.employees)
        self.assertEqual("boss", club.roles[boss])
        self.assertEqual(WAGES["boss"], club.wage_for(boss))
        self.assertTrue(club.is_open)

    def test_defaults(self):
        club = Brothel(boss=Person())
        self.assertEqual(("Brothel", 10, {"stamina": 2}), (club.name, club.price, club.effects))
        self.assertEqual("BR", str(club))
        self.assertEqual((0, 0), (club.visits, club.revenue))

    def test_the_town_knows_it_as_a_leisure_place_and_a_workplace(self):
        town, club, _ = make_club()
        self.assertEqual([club], town.leisure_buildings)
        self.assertIn(club, town.work_buildings)
        self.assertNotIn(club, town.shop_buildings)

    def test_a_town_hands_out_the_leisure_place_to_new_grown_ups(self):
        town, club, _ = make_club()
        person = Person(name="New")
        town.add_citizen(person)
        town.integrate_adult(person)
        self.assertIs(club, person.leisure_spot)


class TestStaff(unittest.TestCase):

    def setUp(self):
        self.town, self.club, self.boss = make_club(work_places=3)

    def test_grown_ups_can_work_there(self):
        worker = Person(name="Worker")
        self.assertTrue(self.club.employ(worker))
        self.assertIs(self.club, worker.workplace)

    def test_children_cannot(self):
        child = Person(name="Child", age=ADULT_AGE - 1)
        self.assertFalse(self.club.employ(child))
        self.assertIsNone(child.workplace)
        self.assertNotIn(child, self.club.employees)

    def test_the_places_are_limited(self):
        self.assertTrue(self.club.employ(Person()))
        self.assertTrue(self.club.employ(Person()))
        self.assertFalse(self.club.employ(Person()))         # the boss has the first of three

    def test_nobody_has_two_jobs(self):
        factory = WorkBuilding("Factory")
        worker = Person()
        factory.employ(worker)
        self.assertFalse(self.club.employ(worker))
        self.assertEqual([], [p for p in self.club.employees if p is worker])

    def test_a_grown_up_who_works_somewhere_is_not_taken_a_second_time_by_the_town(self):
        factory = WorkBuilding("Factory", work_places=5)
        self.town.add_building(factory)
        person = Person(name="Worker")
        self.town.add_citizen(person)
        self.club.employ(person)

        self.town.integrate_adult(person)

        self.assertIs(self.club, person.workplace)
        self.assertNotIn(person, factory.employees)

    def test_staff_gets_the_wages(self):
        worker = Person(name="Worker", routine=1)
        self.club.employ(worker)
        worker.go(self.club)

        self.club.update(DayTime.NOON)          # routine 1: WORK

        self.assertEqual(WAGES["worker"], worker.money())

    def test_the_boss_earns_the_boss_wage(self):
        self.boss.go(self.club)
        self.club.update(DayTime.NOON)
        self.assertEqual(WAGES["boss"], self.boss.money())

    def test_without_a_boss_it_is_closed_and_pays_nobody(self):
        worker = Person(name="Worker", routine=1)
        self.club.employ(worker)
        worker.go(self.club)

        self.boss.die("old age")

        self.assertIsNone(self.club.boss)
        self.assertFalse(self.club.is_open)
        self.club.update(DayTime.NOON)
        self.assertEqual(0, worker.money())

    def test_a_new_boss_opens_it_again(self):
        self.boss.die("old age")
        successor = Person(name="Successor")

        self.club.appoint_boss(successor)

        self.assertTrue(self.club.is_open)
        self.assertIs(successor, self.club.boss)
        self.assertEqual("boss", self.club.roles[successor])
        self.assertIs(self.club, successor.workplace)
        self.assertEqual(WAGES["boss"], self.club.wage_for(successor))

    def test_an_employee_can_become_the_boss(self):
        worker = Person(name="Worker")
        self.club.employ(worker)
        self.boss.die("old age")

        self.club.appoint_boss(worker)

        self.assertEqual(1, self.club.employees.count(worker))
        self.assertEqual("boss", self.club.roles[worker])

    def test_appointing_a_boss_is_checked(self):
        with self.assertRaisesRegex(ValueError, "has a boss already"):
            self.club.appoint_boss(Person())

        self.boss.die("old age")
        with self.assertRaisesRegex(ValueError, "living grown up"):
            self.club.appoint_boss(Person(age=ADULT_AGE - 1))
        dead = Person()
        dead.die()
        with self.assertRaisesRegex(ValueError, "living grown up"):
            self.club.appoint_boss(dead)
        busy = Person()
        WorkBuilding("Factory").employ(busy)
        with self.assertRaisesRegex(ValueError, "somewhere else"):
            self.club.appoint_boss(busy)

    def test_no_free_place_for_the_new_boss(self):
        town, club, boss = make_club(work_places=2)
        club.employ(Person())
        boss.die("old age")             # the boss place is free again, so one place is left ...
        club.employ(Person())           # ... and taken
        with self.assertRaisesRegex(ValueError, "no free work place"):
            club.appoint_boss(Person())


class TestHiring(unittest.TestCase):
    """new grown ups go where the fewest places are taken, so that no workplace stays empty for good"""

    def setUp(self):
        self.town, self.club, self.boss = make_club(work_places=10)
        self.factory = WorkBuilding("Factory", work_places=10)
        self.town.add_building(self.factory)

    def fill(self, building, number):
        for _ in range(number):
            building.employ(Person())

    def new_grown_up(self):
        person = Person(name="New")
        self.town.add_citizen(person)
        self.town.integrate_adult(person)
        return person

    def test_the_emptier_workplace_gets_him(self):
        self.fill(self.factory, 5)                         # factory 5/10, club 1/10 (the boss)
        self.assertIs(self.club, self.new_grown_up().workplace)

        self.fill(self.club, 6)                            # club 8/10 now
        self.assertIs(self.factory, self.new_grown_up().workplace)

    def test_at_the_same_level_the_first_one_wins(self):
        town = TownHall("T")
        first, second = WorkBuilding("First", work_places=4), WorkBuilding("Second", work_places=8)
        town.add_building(first)
        town.add_building(second)
        person = Person()
        town.add_citizen(person)
        town.integrate_adult(person)
        self.assertIs(first, person.workplace)

    def test_places_are_filled_evenly_not_one_after_the_other(self):
        for _ in range(18):
            self.new_grown_up()
        self.assertEqual((10, 9), (len(self.club.employees), len(self.factory.employees)))   # 10/10 and 9/10, boss included

    def test_a_full_workplace_is_skipped(self):
        self.fill(self.club, 9)                            # full with the boss
        self.fill(self.factory, 3)
        self.assertIs(self.factory, self.new_grown_up().workplace)

    def test_a_closed_brothel_gets_nobody(self):
        self.boss.die("old age")
        for _ in range(5):
            self.assertIs(self.factory, self.new_grown_up().workplace)
        self.assertEqual([], self.club.employees)

    def test_when_everything_is_full_he_has_no_job(self):
        self.fill(self.club, 9)
        self.fill(self.factory, 10)
        self.assertIsNone(self.new_grown_up().workplace)

    def test_somebody_who_works_already_keeps_the_job(self):
        worker = Person(name="Worker")
        self.town.add_citizen(worker)
        self.factory.employ(worker)
        self.town.integrate_adult(worker)
        self.assertIs(self.factory, worker.workplace)
        self.assertEqual(1, self.factory.employees.count(worker))
        self.assertNotIn(worker, self.club.employees)

    def test_a_freed_place_is_filled_again_in_the_simulation(self):
        # a town with a brothel next to a factory and a shop (without a shop nobody could eat):
        # when the staff dies the places do not stay empty, the brothel is staffed like the others
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                random.seed(seed)
                town = TownHall("Thintown")
                town.add_building(MegaBuilding("Homes", stories=20, persons_per_unit=10, health=1, stamina=2,
                                               hunger=0, money=0))
                factory = WorkBuilding("Factory", work_places=100)
                town.add_building(factory)
                town.add_building(Shop("Shop", work_places=100))
                boss = Maxima()
                town.add_citizen(boss)
                boss.find_place_to_live(town.list_of_buildings())
                club = Brothel("Club", boss=boss, work_places=20, price=0)
                town.add_building(club)
                for _ in range(150):
                    person = Person(age=random.randint(0, 89))
                    town.add_citizen(person)
                    person.find_place_to_live(town.list_of_buildings())
                    if person.is_adult:
                        town.integrate_adult(person)
                sim = Simulation(town)

                starting_staff = len(club.employees)
                self.assertGreater(starting_staff, 5)
                for target in (100, 150, 200):
                    sim.run(target - sim.cycle)
                    level_club = len(club.employees) / club.work_places
                    level_factory = len(factory.employees) / factory.work_places
                    self.assertGreater(len(club.employees), starting_staff / 2, f"cycle {target}")
                    self.assertGreater(len(club.employees), 5, f"cycle {target}")
                    self.assertLess(abs(level_club - level_factory), 0.25, f"cycle {target}")


class TestVisiting(unittest.TestCase):

    def setUp(self):
        self.town, self.club, self.boss = make_club(price=10)

    def test_who_is_let_in(self):
        rich = guest(self.town, "Rich", money=10)
        poor = guest(self.town, "Poor", money=9)
        child = guest(self.town, "Child", money=1000, age=ADULT_AGE - 1)
        staff = guest(self.town, "Staff", money=0)
        self.club.employ(staff)

        self.assertTrue(self.club.admits(rich))
        self.assertFalse(self.club.admits(poor))
        self.assertFalse(self.club.admits(child))
        self.assertTrue(self.club.admits(staff))           # staff pays nothing
        self.assertTrue(self.club.admits(self.boss))

    def test_nobody_is_let_in_when_it_is_closed_or_the_sim_is_dead(self):
        rich = guest(self.town, "Rich")
        self.assertTrue(self.club.admits(rich))

        self.boss.die("old age")
        self.assertFalse(self.club.admits(rich))

        self.club.appoint_boss(Person())
        rich.die()
        self.assertFalse(self.club.admits(rich))

    def test_a_visit(self):
        person = guest(self.town, "Visitor", money=25)
        person.attributes.stamina = 5
        person.go(self.club)

        self.assertTrue(person.relax(DayTime.EVENING))

        self.assertEqual(15, person.money())
        self.assertEqual(7, person.attributes.stamina)
        self.assertEqual((1, 10), (self.club.visits, self.club.revenue))
        self.assertEqual(10, person.totals["leisure_spent"])
        self.assertEqual(10, self.town.ledger.today["leisure_spent"])
        self.assertEqual((1, "EVENING", "visited Club for 10"), person.log[-1])

    def test_effects_stay_inside_the_limits(self):
        person = guest(self.town, "Visitor")
        person.go(self.club)
        person.relax()
        self.assertEqual(10, person.attributes.stamina)

    def test_staff_pays_nothing(self):
        worker = guest(self.town, "Worker", money=0)
        self.club.employ(worker)
        worker.go(self.club)

        self.assertTrue(worker.relax(DayTime.EVENING))

        self.assertEqual(0, worker.money())
        self.assertEqual((1, 0), (self.club.visits, self.club.revenue))
        self.assertEqual("visited Club", worker.log[-1][2])
        self.assertEqual(0, worker.totals["leisure_spent"])

    def test_the_boss_with_infinite_money_loses_nothing(self):
        maxima = Maxima()
        self.town.add_citizen(maxima)
        club = Brothel("Maxima's Club", boss=maxima, price=10)
        maxima.find_leisure_spot([club])
        maxima.go(club)
        maxima.relax()
        self.assertEqual(math.inf, maxima.money())

    def test_relaxing_only_works_in_the_leisure_place(self):
        person = guest(self.town, "Visitor")
        person.go(person.home)
        self.assertFalse(person.relax())
        self.assertEqual(100, person.money())

    def test_not_admitted_means_no_visit(self):
        poor = guest(self.town, "Poor", money=3)
        poor.go(self.club)
        self.assertFalse(poor.relax())
        self.assertEqual(0, self.club.visits)

    def test_a_sim_goes_where_it_is_let_in(self):
        person = guest(self.town, "Visitor")
        self.assertIs(self.club, person.destination_for(ActionType.GO_TO_LEISURE))
        self.assertIs(self.club, person.destination_for(ActionType.LEISURE))

    def test_a_sim_who_cannot_pay_stays_home(self):
        poor = guest(self.town, "Poor", money=3)
        self.assertIs(poor.home, poor.destination_for(ActionType.LEISURE))

    def test_children_never_go_there(self):
        child = guest(self.town, "Child", money=1000, age=ADULT_AGE - 1)
        self.assertIs(self.club, child.leisure_spot)             # even if somebody gave it to them
        self.assertIs(child.home, child.destination_for(ActionType.GO_TO_LEISURE))
        self.assertIs(child.home, child.destination_for(ActionType.LEISURE))

    def test_a_closed_club_keeps_everybody_at_home(self):
        person = guest(self.town, "Visitor")
        self.boss.die("old age")
        self.assertIs(person.home, person.destination_for(ActionType.LEISURE))

    def test_no_leisure_place_no_visit(self):
        person = Person(name="Nobody")
        self.assertFalse(person.find_leisure_spot([]))
        self.assertIsNone(person.leisure_spot)

    def test_the_visit_is_paid_once_not_twice(self):
        person = guest(self.town, "Visitor")
        person.go(person.home)

        person.action(DayTime.AFTERNOON_MOVEMENT)       # GO_TO_LEISURE: on the way
        self.assertIs(self.club, person.current_location)
        self.assertEqual(100, person.money())

        person.action(DayTime.EVENING)                  # LEISURE: there, and pays
        self.assertEqual(90, person.money())
        self.assertEqual(1, self.club.visits)

    def test_a_visitor_who_ran_out_of_money_on_the_way_goes_home_again(self):
        person = guest(self.town, "Visitor", money=10)
        person.action(DayTime.AFTERNOON_MOVEMENT)
        self.assertIs(self.club, person.current_location)

        person.attributes += Stats(money=-5)            # spent it on the way
        person.action(DayTime.EVENING)

        self.assertIs(person.home, person.current_location)
        self.assertEqual(0, self.club.visits)


class TestInTheTown(unittest.TestCase):

    def test_every_grown_up_comes_once_a_day(self):
        town, club, boss = make_club(price=10)
        visitors = [guest(town, f"V{n}", routine=1 + n % 5) for n in range(10)]
        sim = Simulation(town)

        sim.run(1)

        self.assertEqual(10 + 1, club.visits)               # the boss comes too
        self.assertEqual(10 * 10, club.revenue)             # only the guests pay
        self.assertTrue(all(v.money() == 90 for v in visitors))

    def test_the_census_shows_who_is_there(self):
        town, club, boss = make_club()
        guest(town, "V")
        sim = Simulation(town)

        seen = set()
        for _ in range(10):
            sim.step()
            seen.add(sim.census().get("Club", 0))

        self.assertIn(0, seen)
        self.assertTrue(max(seen) >= 1)

    def test_children_never_show_up(self):
        town, club, boss = make_club()
        child = guest(town, "Child", age=ADULT_AGE - 1)
        sim = Simulation(town)

        for _ in range(10):
            sim.step()
            self.assertIsNot(club, child.current_location)
        self.assertEqual(1, club.visits)                    # only the boss

    def test_the_boss_works_and_is_paid(self):
        town, club, boss = make_club()
        sim = Simulation(town)
        sim.run(1)
        self.assertEqual(WAGES["boss"], boss.totals["money_earned"])

    def test_a_dead_boss_closes_the_club_until_there_is_a_new_one(self):
        town, club, boss = make_club()
        visitor = guest(town, "Visitor")
        sim = Simulation(town)
        sim.run(1)
        visits = club.visits
        self.assertGreater(visits, 0)

        boss.die("old age")
        sim.run(2)
        self.assertEqual(visits, club.visits)
        self.assertEqual(100 - 10, visitor.money())          # paid once, on the first day

        club.appoint_boss(Person(name="Successor"))
        sim.run(1)
        self.assertEqual(visits + 1, club.visits)

    def test_the_people_who_relax_together_there_can_meet(self):
        # different homes, so they could never meet at home
        def pregnancies(with_club):
            town = TownHall("T")
            town.add_building(MegaBuilding("Homes", stories=4, persons_per_unit=1, health=1, stamina=2, hunger=0, money=0))
            town.add_building(MegaBuilding("Spare", stories=1, persons_per_unit=5, health=0, stamina=0, hunger=-1, money=0))
            people = []
            if with_club:
                boss = Person(name="Boss", age=60)              # too old to mate
                town.add_citizen(boss)
                boss.find_place_to_live(town.list_of_buildings())
                town.add_building(Brothel("Club", boss=boss, price=0))
            for name, gender in (("Ann", "female"), ("Bob", "male")):
                person = Person(name=name, age=25, routine=1, gender=gender)
                town.add_citizen(person)
                person.find_place_to_live(town.list_of_buildings())
                if with_club:
                    person.find_leisure_spot(town.leisure_buildings)
                people.append(person)
            sim = Simulation(town)
            with always_mate():
                sim.run(1)
            return reproduction.pregnant_count(town)

        self.assertEqual(1, pregnancies(with_club=True))
        self.assertEqual(0, pregnancies(with_club=False))

    def test_a_thin_town_survives_when_everybody_meets_at_the_brothel(self):
        # 100 sims on 200 places: living with each other alone is not enough to keep a town alive
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                random.seed(seed)
                town = TownHall("Thintown")
                town.add_building(MegaBuilding("Homes", stories=20, persons_per_unit=10, health=1, stamina=2,
                                               hunger=0, money=0))
                town.add_building(WorkBuilding("Factory", work_places=200))
                town.add_building(Shop("Shop", work_places=200))
                boss = Maxima()
                town.add_citizen(boss)
                boss.find_place_to_live(town.list_of_buildings())
                town.add_building(Brothel("Club", boss=boss, work_places=200, price=0))
                for _ in range(100):
                    person = Person(age=random.randint(0, 89))
                    town.add_citizen(person)
                    person.find_place_to_live(town.list_of_buildings())
                    if person.is_adult:
                        town.integrate_adult(person)
                sim = Simulation(town)

                low = len(sim.living())
                for _ in range(250):
                    sim.run_cycle()
                    low = min(low, len(sim.living()))

                self.assertGreater(len(sim.living()), 100)
                self.assertGreater(low, 60)

    def test_the_club_survives_saving(self):
        town, club, boss = make_club()
        visitor = guest(town, "Visitor")
        sim = Simulation(town)
        sim.run(2)
        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        loaded_club = loaded.town_hall.leisure_buildings[0]
        self.assertEqual((club.visits, club.revenue, club.price), (loaded_club.visits, loaded_club.revenue, loaded_club.price))
        self.assertEqual("Boss", loaded_club.boss.name)
        self.assertTrue(loaded_club.is_open)
        loaded_visitor = next(p for p in loaded.town_hall.citizens if p.name == "Visitor")
        self.assertIs(loaded_club, loaded_visitor.leisure_spot)

        sim.run(2)
        loaded.run(2)
        self.assertEqual((club.visits, club.revenue), (loaded_club.visits, loaded_club.revenue))


class TestMaximaAndAges(unittest.TestCase):

    def test_maxima_can_mate_at_every_age_from_adulthood_on(self):
        maxima = Maxima()
        for age in (ADULT_AGE, 50, 51, 100, 1000, 10 ** 6):
            with self.subTest(age=age):
                maxima.age = age
                self.assertTrue(maxima.can_mate())

    def test_maxima_is_no_exception_for_children(self):
        maxima = Maxima()
        maxima.age = ADULT_AGE - 1
        self.assertFalse(maxima.can_mate())
        maxima.age = 0
        self.assertFalse(maxima.can_mate())

    def test_the_others_stop_at_the_end_of_the_fertile_ages(self):
        person = Person()
        person.age = 51
        self.assertFalse(person.can_mate())
        person.age = 50
        self.assertTrue(person.can_mate())

    def test_a_sim_with_its_own_range(self):
        person = Person(fertile_ages=(20, 60))
        person.age = 19
        self.assertFalse(person.can_mate())
        person.age = 60
        self.assertTrue(person.can_mate())
        person.age = 61
        self.assertFalse(person.can_mate())

    def test_no_range_can_start_below_adulthood(self):
        for bad in ((ADULT_AGE - 1, 50), (0, 50), (10, math.inf), (20, 19), (20,), (20, 30, 40)):
            with self.subTest(range=bad), self.assertRaises(ValueError):
                Person(fertile_ages=bad)
        self.assertEqual((ADULT_AGE, math.inf), Person(fertile_ages=(ADULT_AGE, math.inf)).fertile_ages)

    def test_a_tampered_range_still_cannot_make_a_child_fertile(self):
        child = Person(age=10)
        child.fertile_ages = (0, 100)
        self.assertFalse(child.can_mate())

    def test_maxima_can_carry_a_baby_of_a_male_at_any_age(self):
        town, club, _ = make_club(spare=3)
        maxima = Maxima()
        maxima.age = 500
        town.add_citizen(maxima)
        other = guest(town, "Other", age=30)
        other.gender = "male"

        self.assertEqual(1, reproduction.conceive(town, [(maxima, other, DayTime.EVENING)], 1))
        self.assertIsNotNone(maxima.pregnancy)
        self.assertIsNone(other.pregnancy)

    def test_maxima_is_found_by_the_meeting_at_any_age(self):
        town, club, _ = make_club()
        maxima = Maxima()
        maxima.age = 1000
        town.add_citizen(maxima)
        maxima.go(club)
        other = guest(town, "Other")
        other.go(club)

        with always_mate():
            couples = reproduction.meet([maxima, other], DayTime.EVENING)

        self.assertEqual(1, len(couples))
        self.assertIn(maxima, couples[0][:2])

    def test_maxima_does_not_meet_a_child(self):
        town, club, _ = make_club()
        maxima = Maxima()
        town.add_citizen(maxima)
        maxima.go(club)
        child = Person(age=ADULT_AGE - 1)
        town.add_citizen(child)
        child.go(club)

        with always_mate():
            self.assertEqual([], reproduction.meet([maxima, child], DayTime.EVENING))

    def test_the_babys_age_and_lifespan_are_normal(self):
        town, club, _ = make_club(spare=3)
        maxima = Maxima()
        town.add_citizen(maxima)
        other = guest(town, "Other")
        other.gender = "male"
        maxima.become_pregnant(2, other)

        (baby,) = reproduction.give_births(town, 2)

        self.assertEqual(0, baby.age)
        self.assertTrue(90 <= baby.lifespan <= 110)
        self.assertFalse(baby.fertile_ages[1] == math.inf)         # the baby is no Maxima
        self.assertEqual(1, maxima.children)


class TestTheDemoTown(unittest.TestCase):

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            town = main.build_town()
        return town, out.getvalue()

    def test_the_brothel_is_there_with_maxima_as_the_boss(self):
        town, out = self.build()
        (club,) = town.leisure_buildings
        maxima = next(p for p in town.citizens if p.name == "Maxima")

        self.assertEqual("Velvet Room", club.name)
        self.assertIs(maxima, club.boss)
        self.assertIs(club, maxima.workplace)
        self.assertIs(club, maxima.leisure_spot)
        self.assertTrue(club.is_open)
        self.assertRegex(out, r"brothel \d+ \(boss Maxima\)")

    def test_the_staff_are_grown_ups_with_one_job_each(self):
        town, _ = self.build()
        (club,) = town.leisure_buildings

        # it is staffed like the other workplaces (more than 80 percent of its places at the start)
        self.assertGreater(len(club.employees), 0.8 * main.BROTHEL_PLACES)
        self.assertLessEqual(len(club.employees), main.BROTHEL_PLACES)
        self.assertTrue(all(p.is_adult for p in club.employees))
        for building in town.work_buildings:
            for person in building.employees:
                self.assertIs(building, person.workplace)
        everybody = [p for b in town.work_buildings for p in b.employees]
        self.assertEqual(len(everybody), len(set(map(id, everybody))))

    def test_every_grown_up_has_the_leisure_place_children_do_not(self):
        town, _ = self.build()
        (club,) = town.leisure_buildings
        for person in town.citizens:
            if person.is_adult:
                self.assertIs(club, person.leisure_spot, person.name)
            else:
                self.assertIsNone(person.leisure_spot)

    def test_it_runs(self):
        town, _ = self.build()
        sim = Simulation(town)
        sim.run(3)
        (club,) = town.leisure_buildings
        self.assertGreater(club.visits, 1000)
        self.assertTrue(club.is_open)

    def test_maxima_is_still_immortal_and_fertile(self):
        town, _ = self.build()
        maxima = next(p for p in town.citizens if p.name == "Maxima")
        self.assertEqual(math.inf, maxima.lifespan)
        self.assertEqual((ADULT_AGE, math.inf), maxima.fertile_ages)


class TestShowingIt(unittest.TestCase):

    def setUp(self):
        self.town, self.club, self.boss = make_club(price=10)
        self.visitor = guest(self.town, "Visitor")
        self.sim = Simulation(self.town)
        self.sim.run(2)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_the_building_details(self):
        data = self.ask("building", "Club")

        self.assertEqual("brothel", data["kind"])
        self.assertEqual(("Boss", 10, True), (data["boss"], data["price"], data["open"]))
        self.assertEqual({"stamina": 2}, data["effects"])
        self.assertEqual(self.club.visits, data["visits"])
        self.assertEqual((1, 5), (data["employees"], data["capacity"]))

    def test_the_text_for_the_building(self):
        text = console.fmt_building(self.ask("building", "Club"))
        self.assertIn("[brothel, Brothel]", text)
        self.assertIn("boss:       Boss", text)
        self.assertIn("open:       yes", text)
        self.assertIn("entrance:   10 (staff pays nothing), gives stamina +2", text)
        self.assertIn(f"visits:     {self.club.visits}, revenue {self.club.revenue}", text)

    def test_a_closed_club_says_why(self):
        self.boss.die("old age")
        text = console.fmt_building(self.ask("building", "Club"))
        self.assertIn("open:       no, it needs a boss", text)
        self.assertIn("boss:       -", text)

    def test_the_list_of_buildings(self):
        entry = next(b for b in self.ask("buildings")["buildings"] if b["name"] == "Club")
        self.assertEqual(("brothel", 1, 5), (entry["kind"], entry["employees"], entry["capacity"]))

    def test_where_a_visitor_is(self):
        sim = Simulation(self.town)
        while self.ask("where", "Visitor")["action"]["type"] != "LEISURE":
            self.sim.step()
        data = self.ask("where", "Visitor")
        self.assertEqual("Club (brothel)", data["location"]["text"])
        self.assertEqual("relaxing", data["action"]["text"])

    def test_why_somebody_is_at_home_instead(self):
        poor = guest(self.town, "Poor", money=2)
        child = guest(self.town, "Kid", age=ADULT_AGE - 1)
        while self.ask("where", "Poor")["action"]["type"] != "LEISURE":
            self.sim.step()

        self.assertEqual("relaxing (not let in, stays home)", self.ask("where", "Poor")["action"]["text"])
        self.assertEqual("relaxing (too young, stays home)", self.ask("where", "Kid")["action"]["text"])

    def test_the_boss_is_called_boss(self):
        self.assertEqual("boss", self.ask("npc", "Boss")["workplace"]["role"])

    def test_the_money_spent_on_leisure_is_booked(self):
        goods = self.ask("goods")
        self.assertGreater(goods["total"]["leisure_spent"], 0)
        self.assertIn("leisure spent", console.fmt_goods(goods))
        self.assertIn("leisure spent", console.fmt_world(self.ask("world")))

    def test_the_map_knows_it(self):
        cells = {c["name"]: c for c in self.ask("map")["cells"]}
        self.assertEqual(("brothel", "BR"), (cells["Club"]["kind"], cells["Club"]["symbol"]))
        text = console.fmt_map(self.ask("map"))
        self.assertIn("BR", text)
        self.assertIn("BR brothel", text)

    def test_the_window_has_a_color_for_it(self):
        self.assertIn("brothel", display.KIND_COLORS)
        self.assertNotEqual(display.KIND_COLORS["brothel"], display.KIND_COLORS["shop"])

    def test_the_text_stays_plain_ascii(self):
        console.fmt_building(self.ask("building", "Club")).encode("ascii")
        console.fmt_map(self.ask("map")).encode("ascii")
        console.fmt_goods(self.ask("goods")).encode("ascii")


if __name__ == "__main__":
    unittest.main()
