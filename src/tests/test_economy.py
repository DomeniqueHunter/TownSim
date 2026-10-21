
import math
import tempfile
import unittest
from pathlib import Path

from buildings import MegaBuilding, WorkBuilding, Shop, WAGES
from persistence import save_state, load_state
from person import Person, DayTime, ActionType
from person.person import FOOD_STOCK_TARGET
from services import TownHall
from simulation import Simulation
from stats import Stats


def housed_person(name="P", routine=1, money=0, shop=None):
    """a person living in his own home, standing in it"""
    home = MegaBuilding(f"Home of {name}", stories=1, persons_per_unit=1, money=0)
    person = Person(name=name, routine=routine)
    person.attributes += Stats(money=money)
    person.find_place_to_live([home])
    person.go(person.home)
    person.shop = shop
    return person


class TestShop(unittest.TestCase):

    def test_sell_food(self):
        shop = Shop("S", food_price=5)
        person = Person(name="Buyer")
        person.attributes += Stats(money=20)

        self.assertEqual(3, shop.sell_food(person, 3))
        self.assertEqual(5, person.money())
        self.assertEqual(3, person.inventory["food"])
        self.assertEqual(15, shop.revenue)

    def test_cannot_buy_more_than_affordable(self):
        shop = Shop("S", food_price=5)
        person = Person(name="Buyer")
        person.attributes += Stats(money=12)

        self.assertEqual(2, shop.sell_food(person, 10))
        self.assertEqual(2, person.money())

    def test_broke_person_buys_nothing(self):
        shop = Shop("S", food_price=5)
        person = Person(name="Broke")

        self.assertEqual(0, shop.sell_food(person, 3))
        self.assertEqual(0, person.inventory["food"])
        self.assertEqual(0, shop.revenue)

    def test_nonsense_amounts(self):
        shop = Shop("S")
        person = Person(name="Buyer")
        person.attributes += Stats(money=100)

        self.assertEqual(0, shop.sell_food(person, 0))
        self.assertEqual(0, shop.sell_food(person, -3))
        self.assertEqual(100, person.money())

    def test_infinite_money(self):
        shop = Shop("S", food_price=5)
        rich = Person(name="Rich", attributes=None)
        rich.attributes += Stats(money=math.inf)

        self.assertEqual(3, shop.sell_food(rich, 3))
        self.assertEqual(math.inf, rich.money())

    def test_free_food(self):
        shop = Shop("S", food_price=0)
        person = Person(name="Poor")

        self.assertEqual(3, shop.sell_food(person, 3))


class TestBuyingAndEating(unittest.TestCase):

    def test_buys_only_in_the_shop(self):
        shop = Shop("S")
        person = housed_person(money=100, shop=shop)

        self.assertEqual(0, person.buy_food())   # still at home

        person.go(shop)
        self.assertEqual(FOOD_STOCK_TARGET, person.buy_food())

    def test_buys_up_to_stock_target_only(self):
        shop = Shop("S")
        person = housed_person(money=100, shop=shop)
        person.go(shop)
        person.inventory["food"] = FOOD_STOCK_TARGET - 1

        self.assertEqual(1, person.buy_food())
        self.assertEqual(0, person.buy_food())

    def test_no_shop_no_food(self):
        person = housed_person(money=100)
        self.assertEqual(0, person.buy_food())

    def test_eats_at_home(self):
        person = housed_person()
        person.inventory["food"] = 5
        person.attributes += Stats(hunger=3)

        self.assertEqual(3, person.eat())
        self.assertEqual(0, person.attributes.hunger)
        self.assertEqual(2, person.inventory["food"])

    def test_does_not_waste_food_when_not_hungry(self):
        person = housed_person()
        person.inventory["food"] = 5

        self.assertEqual(0, person.eat())
        self.assertEqual(5, person.inventory["food"])

    def test_eats_only_what_it_has(self):
        person = housed_person()
        person.inventory["food"] = 1
        person.attributes += Stats(hunger=4)

        self.assertEqual(1, person.eat())
        self.assertEqual(3, person.attributes.hunger)

    def test_does_not_eat_away_from_home(self):
        shop = Shop("S")
        person = housed_person(shop=shop)
        person.inventory["food"] = 5
        person.attributes += Stats(hunger=3)
        person.go(shop)

        self.assertEqual(0, person.eat())
        self.assertEqual(3, person.attributes.hunger)

    def test_homeless_person_cannot_eat(self):
        person = Person(name="Homeless")
        person.inventory["food"] = 5
        person.attributes += Stats(hunger=3)

        self.assertEqual(0, person.eat())

    def test_meals_and_shopping_follow_the_routine(self):
        shop = Shop("S")
        person = housed_person(money=100, shop=shop)   # routine 1
        person.attributes += Stats(hunger=2)

        person.action(DayTime.MORNING)              # WAKEUP: nothing to eat yet
        self.assertEqual(2, person.attributes.hunger)

        person.action(DayTime.NOON_MOVEMENT)        # GO_TO_SHOP: walks, does not buy
        self.assertIs(shop, person.current_location)
        self.assertEqual(0, person.inventory["food"])

        person.action(DayTime.AFTERNOON)            # SHOP: buys
        self.assertEqual(FOOD_STOCK_TARGET, person.inventory["food"])

        person.action(DayTime.EVENING_MOVEMENT)     # GO_HOME: dinner
        self.assertEqual(0, person.attributes.hunger)
        self.assertEqual(FOOD_STOCK_TARGET - 2, person.inventory["food"])


class TestWages(unittest.TestCase):

    def test_paid_when_working(self):
        job = WorkBuilding("Job")
        worker = housed_person()
        job.employ(worker)
        worker.go(job)

        job.update(DayTime.NOON)            # routine 1: WORK

        self.assertEqual(WAGES["worker"], worker.money())

    def test_not_paid_while_walking_to_work(self):
        job = WorkBuilding("Job")
        worker = housed_person()
        job.employ(worker)
        worker.go(job)

        job.update(DayTime.MORNING_MOVEMENT)   # routine 1: GO_TO_WORK

        self.assertEqual(0, worker.money())

    def test_not_paid_when_somewhere_else(self):
        job = WorkBuilding("Job")
        worker = housed_person()
        job.employ(worker)

        job.update(DayTime.NOON)               # at home

        self.assertEqual(0, worker.money())

    def test_paid_once_per_day(self):
        job = WorkBuilding("Job")
        worker = housed_person()
        job.employ(worker)

        town = TownHall("T")
        town.add_building(job)
        town.add_citizen(worker)
        Simulation(town).run_cycle()

        self.assertEqual(WAGES["worker"], worker.money())

    def test_roles_and_boss(self):
        boss = housed_person("boss")
        clerk = housed_person("clerk")
        worker = housed_person("worker")
        job = WorkBuilding("Job", boss=boss)

        job.employ(boss)
        job.employ(clerk, role="office")
        job.employ(worker)

        self.assertEqual(100, job.wage_for(boss))
        self.assertEqual(50, job.wage_for(clerk))
        self.assertEqual(25, job.wage_for(worker))

    def test_unknown_role(self):
        with self.assertRaises(ValueError):
            WorkBuilding("Job").employ(Person(name="x"), role="king")

    def test_no_place_left(self):
        job = WorkBuilding("Job", work_places=1)

        self.assertTrue(job.employ(Person(name="a")))
        self.assertFalse(job.employ(Person(name="b")))

    def test_dismiss(self):
        job = WorkBuilding("Job")
        worker = Person(name="a")
        job.employ(worker, role="office")

        job.dismiss(worker)

        self.assertEqual([], job.employees)
        self.assertEqual({}, job.roles)
        self.assertIsNone(worker.workplace)


class TestTownEconomy(unittest.TestCase):

    def make_town(self, with_job=True):
        town = TownHall("Testville")
        home = MegaBuilding("Home", stories=2, persons_per_unit=1, money=0)
        job = WorkBuilding("Job")
        shop = Shop("Shop")
        for building in (home, job, shop):
            town.add_building(building)

        worker = Person(name="Worker", routine=1)
        jobless = Person(name="Jobless", routine=1)
        for person in (worker, jobless):
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            person.find_shop(town.shop_buildings)

        if with_job:
            job.employ(worker)

        return town, worker, jobless, shop

    def test_shop_is_registered(self):
        town, _, _, shop = self.make_town()
        self.assertEqual([shop], town.shop_buildings)
        self.assertIn(shop, town.work_buildings)

    def test_worker_survives_jobless_starves(self):
        town, worker, jobless, shop = self.make_town()
        sim = Simulation(town)

        sim.run(30)

        self.assertTrue(worker.alive)
        self.assertLess(worker.attributes.hunger, 3)
        self.assertFalse(jobless.alive)
        self.assertEqual(1, sim.deaths)
        self.assertGreater(shop.revenue, 0)

    def test_jobless_dies_on_day_ten(self):
        town, _, jobless, _ = self.make_town()
        sim = Simulation(town)

        sim.run(9)
        self.assertTrue(jobless.alive)
        sim.run(1)
        self.assertFalse(jobless.alive)

    def test_totals(self):
        town, worker, _, shop = self.make_town()
        sim = Simulation(town)
        sim.run(3)

        totals = sim.totals()
        self.assertEqual(2, totals["alive"])
        self.assertEqual(shop.revenue, totals["revenue"])
        self.assertEqual(sum(p.inventory["food"] for p in town.citizens), totals["food"])

    def test_inventory_survives_save_and_load(self):
        town, worker, _, shop = self.make_town()
        sim = Simulation(town)
        sim.run(3)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "save.pkl"
            save_state(sim, path)
            loaded = load_state(path)

        before = {p.name: (p.inventory["food"], p.money()) for p in town.citizens}
        after = {p.name: (p.inventory["food"], p.money()) for p in loaded.town_hall.citizens}
        self.assertEqual(before, after)
        self.assertEqual(shop.revenue, loaded.town_hall.shop_buildings[0].revenue)

        sim.run(5)
        loaded.run(5)
        self.assertEqual(sim.totals(), loaded.totals())


if __name__ == "__main__":
    unittest.main()
