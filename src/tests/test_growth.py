"""
Growth that only food limits: babies without a free home, a town that builds houses for its homeless,
workplaces that grow, a daily ration of food, and the statistics (homeless, money).
"""

import contextlib
import io
import json
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import console
import main
import queries
import reproduction
from buildings import MegaBuilding, Mansion, WorkBuilding, Shop, Brothel
from client import GameClient, GameError
from gameserver import GameServer
from ledger import Ledger
from person import Person, ADULT_AGE
from person.maxima import Maxima
from persistence import save_state, load_state
from services import TownHall
from services.townhall import HOMELESS_TO_BUILD, BUILD_CYCLES, NEW_HOUSE_STORIES, NEW_HOUSE_PERSONS_PER_UNIT
from simulation import Simulation, money_statistics, PHASES
from stats import Stats

from townhelper import make_sim


def homes(places=10, rent=0, name="Homes"):
    return MegaBuilding(name, stories=1, persons_per_unit=places, health=1, stamina=2, hunger=0, money=-rent)


def homeless_children(town, number, age=5):
    children = []
    for n in range(number):
        child = Person(name=f"kid{n}", age=age, routine=1 + n % 5)
        town.add_citizen(child)
        children.append(child)
    return children


class TestPolicies(unittest.TestCase):

    def test_the_old_behaviour_is_the_default(self):
        town = TownHall("T")
        self.assertEqual((False, False, True), (town.grow_jobs, town.build_houses, town.babies_need_homes))

    def test_they_can_be_chosen(self):
        town = TownHall("T", grow_jobs=True, build_houses=True, babies_need_homes=False)
        self.assertEqual((True, True, False), (town.grow_jobs, town.build_houses, town.babies_need_homes))

    def test_the_demo_town_uses_the_new_ones(self):
        with contextlib.redirect_stdout(io.StringIO()):
            town = main.build_town()
        self.assertEqual((True, True, False), (town.grow_jobs, town.build_houses, town.babies_need_homes))


class TestBabiesWithoutHomes(unittest.TestCase):

    def town(self, babies_need_homes):
        town = TownHall("T", babies_need_homes=babies_need_homes)
        town.add_building(homes(places=2))
        ann = Person(name="Ann", age=25, gender="female")
        bob = Person(name="Bob", age=25, gender="male")
        for person in (ann, bob):
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
        return town, ann, bob

    def test_without_a_free_place_there_is_no_baby_by_default(self):
        town, ann, bob = self.town(babies_need_homes=True)
        self.assertEqual(0, town.free_home_places())
        self.assertEqual(0, reproduction.conceive(town, [(ann, bob, None)], 1))

    def test_a_town_that_builds_does_not_need_the_place(self):
        town, ann, bob = self.town(babies_need_homes=False)
        self.assertEqual(1, reproduction.conceive(town, [(ann, bob, None)], 1))
        self.assertIsNotNone(ann.pregnancy)

    def test_and_there_is_no_limit_for_the_number_of_babies(self):
        town = TownHall("T", babies_need_homes=False)
        couples = []
        for n in range(30):
            mother = Person(name=f"m{n}", age=25, gender="female")
            father = Person(name=f"f{n}", age=25, gender="male")
            town.add_citizen(mother)
            town.add_citizen(father)
            couples.append((mother, father, None))
        self.assertEqual(30, reproduction.conceive(town, couples, 1))

    def test_such_a_baby_is_born_homeless_and_moves_in_later(self):
        town, ann, bob = self.town(babies_need_homes=False)
        reproduction.conceive(town, [(ann, bob, None)], 1)
        (baby,) = reproduction.give_births(town, 3)
        self.assertIsNone(baby.home)
        self.assertEqual([baby], town.homeless())

        self.assertEqual(0, town.house_homeless())          # nothing is free
        town.add_building(homes(places=5, name="New"))
        self.assertEqual(1, town.house_homeless())
        self.assertIsNotNone(baby.home)
        self.assertEqual([], town.homeless())


class TestHomeless(unittest.TestCase):

    def test_who_is_homeless(self):
        town = TownHall("T")
        town.add_building(homes())
        housed = Person(name="Housed")
        town.add_citizen(housed)
        housed.find_place_to_live(town.list_of_buildings())
        nobody = Person(name="Nobody")
        town.add_citizen(nobody)
        dead = Person(name="Dead")
        town.add_citizen(dead)
        dead.die()

        self.assertEqual(["Nobody"], [p.name for p in town.homeless()])

    def test_the_homeless_move_in_where_there_is_room(self):
        town = TownHall("T")
        town.add_building(homes(places=3))
        kids = homeless_children(town, 5)

        self.assertEqual(3, town.house_homeless())
        self.assertEqual(2, len(town.homeless()))
        self.assertEqual(3, sum(1 for kid in kids if kid.home is not None))

    def test_nothing_to_do_without_homeless_or_without_room(self):
        town = TownHall("T")
        self.assertEqual(0, town.house_homeless())
        homeless_children(town, 2)
        self.assertEqual(0, town.house_homeless())

    def test_only_what_they_can_pay(self):
        town = TownHall("T")
        town.add_building(Mansion("Villa", persons_per_unit=2))                  # rent 1000
        poor = Person(name="Poor", age=30)
        rich = Person(name="Rich", age=30)
        rich.attributes += Stats(money=5000)
        town.add_citizen(poor)
        town.add_citizen(rich)

        self.assertEqual(1, town.house_homeless())
        self.assertIsNone(poor.home)
        self.assertEqual("Villa", rich.home.building.name)

    def test_each_cycle_the_simulation_looks_for_homes(self):
        town = TownHall("T")
        kids = homeless_children(town, 2)
        sim = Simulation(town)
        sim.run(1)
        self.assertEqual(2, len(town.homeless()))

        town.add_building(homes(places=5))
        sim.run(1)
        self.assertEqual(0, len(town.homeless()))


class TestBuildingHouses(unittest.TestCase):

    def town(self, homeless, build=True):
        town = TownHall("T", build_houses=build)
        homeless_children(town, homeless)
        return town

    def test_a_few_homeless_do_not_make_the_town_build(self):
        town = self.town(HOMELESS_TO_BUILD - 1)
        town.plan_housing(1)
        self.assertIsNone(town.construction)
        self.assertEqual(0, len(town.news))

    def test_enough_homeless_start_a_house(self):
        town = self.town(HOMELESS_TO_BUILD)
        town.plan_housing(5)

        self.assertEqual({"name": "Housing 1", "ready": 5 + BUILD_CYCLES}, town.construction)
        self.assertEqual([(5, f"building Housing 1 for {HOMELESS_TO_BUILD} homeless sims, ready in cycle {5 + BUILD_CYCLES}")],
                         list(town.news))
        self.assertEqual([], town.home_buildings)            # not there yet

    def test_a_town_that_does_not_build_does_not(self):
        town = self.town(100, build=False)
        town.plan_housing(1)
        self.assertIsNone(town.construction)

    def test_one_house_at_a_time(self):
        town = self.town(100)
        town.plan_housing(1)
        first = dict(town.construction)
        town.plan_housing(2)
        self.assertEqual(first, town.construction)
        self.assertEqual(1, len(town.news))

    def test_the_house_is_ready_after_the_building_time(self):
        town = self.town(HOMELESS_TO_BUILD)
        town.plan_housing(1)
        town.plan_housing(1 + BUILD_CYCLES - 1)
        self.assertEqual([], town.home_buildings)

        town.plan_housing(1 + BUILD_CYCLES)

        (house,) = town.home_buildings
        self.assertEqual("Housing 1", house.name)
        self.assertEqual(NEW_HOUSE_STORIES * NEW_HOUSE_PERSONS_PER_UNIT, house.max_residents)
        self.assertEqual(0, house.rent())                      # free, so the homeless can live there
        self.assertIsNone(town.construction)
        self.assertEqual(1, town.houses_built)
        self.assertIs(house, town.town_grid.grid[tuple(house.address)])        # it stands on the map
        self.assertEqual([], town.homeless())
        self.assertEqual(HOMELESS_TO_BUILD, house.residents())
        self.assertIn(f"Housing 1 is ready: {house.max_residents} places, {HOMELESS_TO_BUILD} homeless sims moved in",
                      town.news[-1][1])

    def test_more_homeless_than_a_house_holds_means_another_house(self):
        capacity = NEW_HOUSE_STORIES * NEW_HOUSE_PERSONS_PER_UNIT
        town = self.town(capacity + HOMELESS_TO_BUILD + 5)
        town.plan_housing(1)
        town.plan_housing(1 + BUILD_CYCLES)
        self.assertEqual(HOMELESS_TO_BUILD + 5, len(town.homeless()))

        town.plan_housing(5)                                    # still enough homeless: the next one is started
        self.assertEqual("Housing 2", town.construction["name"])
        town.plan_housing(5 + BUILD_CYCLES)
        self.assertEqual(["Housing 1", "Housing 2"], [b.name for b in town.home_buildings])
        self.assertEqual([], town.homeless())

    def test_free_places_are_used_before_anything_is_built(self):
        town = self.town(HOMELESS_TO_BUILD + 5)
        town.add_building(homes(places=HOMELESS_TO_BUILD + 5))
        sim = Simulation(town)
        sim.run(2 + BUILD_CYCLES)
        self.assertEqual(0, town.houses_built)
        self.assertEqual([], town.homeless())

    def test_the_simulation_builds_and_the_homeless_move_in(self):
        town = self.town(30)
        sim = Simulation(town)

        sim.run(1)
        self.assertEqual(30, len(town.homeless()))
        self.assertEqual({"name": "Housing 1", "ready": 1 + BUILD_CYCLES}, town.construction)

        sim.run(BUILD_CYCLES)
        self.assertEqual([], town.homeless())
        self.assertEqual(["Housing 1"], [b.name for b in town.home_buildings])
        self.assertTrue(all(kid.alive for kid in town.citizens))

    def test_the_log_tells_what_the_town_does(self):
        town = self.town(30)
        sim = Simulation(town)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(out):
            main.run_cycles(sim, 1 + BUILD_CYCLES, Path(tmp) / "save.pkl")

        lines = out.getvalue().splitlines()
        self.assertIn("cycle 1: alive 30, died 0, new 0, homeless 30,", lines[0])
        self.assertEqual("  town: building Housing 1 for 30 homeless sims, ready in cycle 4", lines[1])
        self.assertTrue(lines[-2].startswith("cycle 4: alive 30, died 0, new 0, homeless 0,"), lines)
        self.assertEqual("  town: Housing 1 is ready: 100 places, 30 homeless sims moved in", lines[-1])

    def test_construction_survives_saving(self):
        town = self.town(30)
        sim = Simulation(town)
        sim.run(1)
        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        self.assertEqual({"name": "Housing 1", "ready": 1 + BUILD_CYCLES}, loaded.town_hall.construction)
        loaded.run(BUILD_CYCLES)
        self.assertEqual(["Housing 1"], [b.name for b in loaded.town_hall.home_buildings])
        self.assertTrue(loaded.town_hall.build_houses)


class TestJobsGrow(unittest.TestCase):

    def town(self, grow=True):
        town = TownHall("T", grow_jobs=grow)
        self.small = WorkBuilding("Small", work_places=1)
        self.big = WorkBuilding("Big", work_places=3)
        town.add_building(self.small)
        town.add_building(self.big)
        for building in (self.small, self.big):
            while building.employ(Person()):
                pass
        return town

    def grown_up(self, town):
        person = Person(name="New")
        town.add_citizen(person)
        town.integrate_adult(person)
        return person

    def test_without_the_policy_he_has_no_job(self):
        town = self.town(grow=False)
        self.assertIsNone(self.grown_up(town).workplace)
        self.assertEqual((1, 3), (self.small.work_places, self.big.work_places))

    def test_the_biggest_workplace_grows_by_a_place(self):
        town = self.town()
        person = self.grown_up(town)

        self.assertIs(self.big, person.workplace)
        self.assertEqual((1, 4), (self.small.work_places, self.big.work_places))
        self.assertEqual(4, len(self.big.employees))

    def test_it_keeps_growing_with_the_town(self):
        town = self.town()
        for _ in range(10):
            self.grown_up(town)
        self.assertEqual(13, self.big.work_places)
        self.assertEqual(13, len(self.big.employees))

    def test_nothing_grows_while_there_are_free_places(self):
        town = TownHall("T", grow_jobs=True)
        place = WorkBuilding("Place", work_places=5)
        town.add_building(place)
        self.grown_up(town)
        self.assertEqual(5, place.work_places)

    def test_a_closed_brothel_does_not_grow_and_is_not_picked(self):
        town = TownHall("T", grow_jobs=True)
        boss = Person(name="Boss")
        town.add_citizen(boss)
        club = Brothel("Club", boss=boss, work_places=50)
        town.add_building(club)
        boss.die("old age")
        person = self.grown_up(town)

        self.assertIsNone(person.workplace)
        self.assertEqual(50, club.work_places)

    def test_a_town_without_workplaces_has_nothing_to_grow(self):
        town = TownHall("T", grow_jobs=True)
        self.assertIsNone(self.grown_up(town).workplace)


class TestDailyRation(unittest.TestCase):

    def test_the_shelf_starts_with_one_ration(self):
        shop = Shop("S", food_per_cycle=100)
        self.assertEqual(100, shop.stock["food"].quantity)
        self.assertEqual(100, shop.food_per_cycle)

    def test_without_a_ration_it_never_runs_out(self):
        shop = Shop("S")
        self.assertIsNone(shop.food_per_cycle)
        self.assertEqual(math.inf, shop.stock["food"].quantity)
        self.assertEqual(0, shop.supply(0))
        self.assertEqual(math.inf, shop.stock["food"].quantity)

    def test_a_shop_without_plain_food_gets_none(self):
        shop = Shop("S", default_food=False, food_per_cycle=100)
        self.assertEqual(0, shop.supply(0))
        self.assertEqual({}, shop.stock)

    def test_the_ration_arrives_in_equal_parts_over_the_day(self):
        for ration in (10, 15, 1200, 7, 1):
            with self.subTest(ration=ration):
                shop = Shop("S", food_per_cycle=ration)
                shop.stock["food"].quantity = 0
                arrived = [shop.supply(i, len(PHASES)) for i in range(len(PHASES))]
                self.assertEqual(ration, sum(arrived))
                self.assertLessEqual(max(arrived) - min(arrived), 1)

    def test_the_shelf_holds_one_ration_at_most(self):
        shop = Shop("S", food_per_cycle=100)
        for _ in range(3):                               # nobody buys anything for three days
            for i in range(len(PHASES)):
                shop.supply(i, len(PHASES))
        self.assertEqual(100, shop.stock["food"].quantity)

    def test_what_was_delivered_in_a_file_is_not_cut(self):
        shop = Shop("S", food_per_cycle=100)
        shop.restock("food", 5, 5000)
        shop.supply(0)
        self.assertEqual(5100, shop.stock["food"].quantity)

    def test_after_everything_was_sold_a_day_refills_exactly_one_ration(self):
        shop = Shop("S", food_per_cycle=100)
        shop.stock["food"].quantity = 0
        for i in range(len(PHASES)):
            shop.supply(i, len(PHASES))
        self.assertEqual(100, shop.stock["food"].quantity)

    def test_the_simulation_brings_the_food_in_every_phase(self):
        town = TownHall("T")
        shop = Shop("S", food_per_cycle=100)
        town.add_building(shop)
        sim = Simulation(town)
        shop.stock["food"].quantity = 0

        seen = []
        for _ in range(len(PHASES)):
            sim.step()
            seen.append(shop.stock["food"].quantity)

        self.assertEqual(100, seen[-1])
        self.assertEqual(sorted(seen), seen)             # more and more arrives, nobody is there to buy it

    def town(self, adults, ration):
        town = TownHall("T")
        town.add_building(homes(places=adults + 10))
        town.add_building(WorkBuilding("Job", work_places=adults))
        town.add_building(Shop("Shop", work_places=1, food_per_cycle=ration))
        people = []
        for n in range(adults):
            person = Person(name=f"p{n}", age=25, routine=1 + n % 5, gender="male" if n % 2 else "female")
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            town.integrate_adult(person)
            people.append(person)
        return town, people

    def test_enough_food_means_nobody_starves(self):
        random.seed(5)
        town, people = self.town(50, ration=60)
        sim = Simulation(town)
        with mock.patch.object(reproduction, "MATE_CHANCE", 0.0):
            sim.run(40)
        self.assertEqual(0, sim.deaths)

    def test_too_little_food_means_some_starve_and_it_hits_everybody_alike(self):
        random.seed(5)
        town, people = self.town(50, ration=30)
        sim = Simulation(town)
        with mock.patch.object(reproduction, "MATE_CHANCE", 0.0):
            sim.run(60)

        starved = [grave.name for grave in town.graveyard if grave.cause == "starvation"]
        routines = {next(p.routine_id for p in people if p.name == name) for name in starved}
        self.assertGreater(len(starved), 5)
        self.assertGreater(len(sim.living()), 5)                # not all of them: 30 pieces a day keep many alive
        self.assertGreaterEqual(len(routines), 4, "it always hits the same ones")

    def test_the_order_at_the_shop_is_random(self):
        town, people = self.town(8, ration=100)
        sim = Simulation(town)
        orders = set()
        original = Person.action

        def spy(person, phase):
            order.append(person.name)
            return original(person, phase)

        with mock.patch.object(Person, "action", spy):
            for _ in range(20):
                order = []
                sim.step()
                orders.add(tuple(order))
                self.assertEqual(sorted(p.name for p in people), sorted(order))      # everybody acts once per phase
        self.assertGreater(len(orders), 5)


class TestMoneyStatistics(unittest.TestCase):

    def people(self, amounts, children=(), rich=1):
        town = TownHall("T")
        town.add_building(homes(places=50))
        people = []
        for number, amount in enumerate(amounts):
            person = Person(name=f"a{number}", age=30)
            person.attributes += Stats(money=amount)
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            people.append(person)
        for number, amount in enumerate(children):
            child = Person(name=f"c{number}", age=5)
            child.attributes += Stats(money=amount)
            town.add_citizen(child)
            child.find_place_to_live(town.list_of_buildings())
            people.append(child)
        for _ in range(rich):
            people.append(Maxima())
            town.add_citizen(people[-1])
            people[-1].find_place_to_live(town.list_of_buildings())
        return town, people

    def test_min_max_avg_of_the_grown_ups(self):
        _, people = self.people([0, 10, 20, 30])
        self.assertEqual({"count": 4, "min": 0, "max": 30, "avg": 15.0}, money_statistics(people))

    def test_maxima_and_the_children_are_left_out(self):
        _, people = self.people([10, 20], children=[1000, 2000])
        self.assertEqual({"count": 2, "min": 10, "max": 20, "avg": 15.0}, money_statistics(people))

    def test_nobody_to_count(self):
        _, people = self.people([], children=[5])
        self.assertEqual({"count": 0, "min": 0, "max": 0, "avg": 0.0}, money_statistics(people))
        self.assertEqual({"count": 0, "min": 0, "max": 0, "avg": 0.0}, money_statistics([]))

    def test_the_average_is_rounded(self):
        _, people = self.people([1, 1, 2])
        self.assertEqual(1.33, money_statistics(people)["avg"])

    def test_every_finished_day_is_in_the_ledger(self):
        town, people = self.people([0, 10, 20, 30], children=[7], rich=1)
        sim = Simulation(town)
        sim.run(2)

        history = list(town.ledger.history)
        self.assertEqual([1, 2], [h["day"] for h in history])
        for entry in history:
            self.assertEqual((4, 0, 30, 15.0), (entry["money_sims"], entry["money_min"], entry["money_max"], entry["money_avg"]))
            self.assertEqual(0, entry["homeless"])

    def test_the_ledger_also_counts_the_homeless(self):
        town = TownHall("T")
        homeless_children(town, 3)
        sim = Simulation(town)
        sim.run(1)
        self.assertEqual(3, town.ledger.history[-1]["homeless"])


class TestQueriesAndConsole(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        # no free place anywhere, so the three children stay homeless (and the town does not build in this test)
        for building in self.sim.town_hall.home_buildings:
            for unit in building.units.values():
                while unit.has_room():
                    unit.claim(Person(name=f"filler-{id(unit)}-{len(unit.owners)}"))
        homeless_children(self.sim.town_hall, 3)
        self.sim.run(3)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_the_world_counts_the_homeless(self):
        population = self.ask("world")["population"]
        self.assertEqual(3, population["homeless"])
        self.assertEqual(3, population["homeless_children"])

    def test_the_text_for_the_world(self):
        self.assertIn("homeless:   3 (3 of them children)", console.fmt_world(self.ask("world")))

    def test_totals_know_the_homeless(self):
        self.assertEqual(3, self.sim.totals()["homeless"])

    def test_money_now_and_per_day(self):
        data = self.ask("money")
        living = [p for p in self.sim.living() if p.is_adult and p.money() != math.inf]
        amounts = [p.money() for p in living]

        self.assertEqual({"count": len(living), "min": min(amounts), "max": max(amounts),
                          "avg": round(sum(amounts) / len(amounts), 2)}, data["now"])
        self.assertEqual((3, 1), (data["children"], data["unlimited"]))
        self.assertEqual([1, 2, 3], [h["day"] for h in data["history"]])
        for row in data["history"]:
            self.assertEqual(set(row), {"day", "sims", "min", "max", "avg", "earned_avg", "spent_avg"})
            self.assertLessEqual(row["min"], row["avg"])
            self.assertLessEqual(row["avg"], row["max"])

    def test_maxima_is_not_in_the_numbers(self):
        data = self.ask("money")
        self.assertNotEqual(math.inf, data["now"]["max"])
        self.assertTrue(all(row["max"] != math.inf for row in data["history"]))

    def test_the_average_earnings_and_spending_per_day(self):
        row = self.ask("money")["history"][-1]
        entry = self.sim.town_hall.ledger.history[-1]
        spent = entry["money_spent"] + entry["leisure_spent"]
        self.assertEqual(round(entry["wages_paid"] / row["sims"], 2), row["earned_avg"])
        self.assertEqual(round(spent / row["sims"], 2), row["spent_avg"])
        self.assertGreater(row["earned_avg"], 0)

    def test_the_number_of_days(self):
        self.assertEqual(2, len(self.ask("money", "2")["history"]))
        self.assertEqual(3, len(self.ask("money", "50")["history"]))
        self.assertEqual(1, len(self.ask("money", "0")["history"]))        # at least one

    def test_a_bad_number_of_days(self):
        with self.assertRaisesRegex(queries.QueryError, "'many' is not a number"):
            self.ask("money", "many")

    def test_before_the_first_day_has_ended(self):
        sim = make_sim()
        data = queries.run(sim, "money", [])
        self.assertEqual([], data["history"])
        self.assertIn("(no finished day yet)", console.fmt_money(data))

    def test_the_text(self):
        lines = console.fmt_money(self.ask("money")).splitlines()
        self.assertRegex(lines[0], r"^money of \d+ grown ups now \(not counted: 1 with unlimited money, 3 children\)$")
        self.assertRegex(lines[1], r"^  min \d+, max \d+, avg \d+\.\d\d$")
        self.assertIn("each of the last 3 days", lines[3])
        self.assertEqual(["day", "grown", "ups", "min", "max", "avg", "earned", "spent"], lines[4].split())
        self.assertEqual(3, len(lines) - 5)

    def test_no_note_when_nobody_is_left_out(self):
        sim = make_sim()
        sim.town_hall.citizens[:] = [p for p in sim.town_hall.citizens if p.name != "Maxima"]
        text = console.fmt_money(queries.run(sim, "money", []))
        self.assertNotIn("not counted", text)

    def test_plain_ascii_and_json(self):
        console.fmt_money(self.ask("money")).encode("ascii")
        console.fmt_world(self.ask("world")).encode("ascii")
        json.dumps(self.ask("money"))

    def test_the_command_is_there(self):
        server = GameServer(self.sim, port=0)
        server.start()
        self.addCleanup(server.stop)
        client = GameClient(port=server.port, timeout=3)
        self.addCleanup(client.close)

        lines = []
        console.execute(client, ["money", "2"], out=lines.append)
        self.assertTrue(lines[0].startswith("money of "))
        lines = []
        console.execute(client, ["help"], out=lines.append)
        self.assertIn("money", "\n".join(lines))
        with self.assertRaises(GameError):
            console.execute(client, ["money", "x"])


class TestTheDemoTown(unittest.TestCase):

    def test_the_numbers(self):
        self.assertEqual(0.09, reproduction.MATE_CHANCE)
        self.assertEqual(1200, main.FOOD_PER_CYCLE)

    def test_the_shop_has_a_daily_ration(self):
        with contextlib.redirect_stdout(io.StringIO()):
            town = main.build_town()
        (shop,) = town.shop_buildings
        self.assertEqual(main.FOOD_PER_CYCLE, shop.food_per_cycle)

    def test_it_grows_slowly_builds_houses_and_nobody_goes_hungry_at_first(self):
        random.seed(3)
        with contextlib.redirect_stdout(io.StringIO()):
            town = main.build_town()
        sim = Simulation(town)
        start = len(sim.living())

        sim.run(40)

        grown = len(sim.living()) / start
        self.assertTrue(1.0 < grown < 1.3, grown)               # a few percent more per ten cycles, not a boom
        self.assertGreaterEqual(town.houses_built, 1)           # the babies needed homes, so the town built
        self.assertLess(len(town.homeless()), 60)
        # 1200 pieces are plenty yet: the only one who starves is Minimus, who has no job and spends his savings
        self.assertEqual({"Minimus"}, {g.name for g in town.graveyard if g.cause == "starvation"})


if __name__ == "__main__":
    unittest.main()
