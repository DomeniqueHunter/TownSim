
import math
import tempfile
import unittest
from pathlib import Path

from buildings import MegaBuilding, WorkBuilding, Shop
from buildings.shop import Offer
from items import ItemDef
from persistence import save_state, load_state
from person import Person
from person.person import FOOD_STOCK_TARGET
from services import TownHall
from simulation import Simulation
from stats import Stats


BREAD = ItemDef("bread", "Bread", "food", {"hunger": -2})
CAKE = ItemDef("cake", "Cake", "food", {"hunger": -3, "health": 2})


def make_shopper(money=100, shop=None, items=(BREAD, CAKE)):
    """a sim with money who stands in a shop; returns (town, shop, person)"""
    town = TownHall("T")
    shop = shop or Shop("S", food_price=5)
    town.add_building(shop)
    town.add_building(MegaBuilding("H", stories=1, persons_per_unit=2, health=1, stamina=2, hunger=0, money=0))
    for item in items:
        town.catalog.add(item)

    person = Person(name="P", routine=1)
    person.attributes += Stats(money=money)
    town.add_citizen(person)
    person.find_place_to_live(town.list_of_buildings())
    person.find_shop(town.shop_buildings)
    person.go(shop)
    return town, shop, person


def at_home(person):
    person.go(person.home)


class TestShopStock(unittest.TestCase):

    def test_a_shop_starts_with_the_plain_food(self):
        shop = Shop("S", food_price=5)

        self.assertEqual(["food"], list(shop.stock))
        self.assertEqual((5, math.inf), (shop.stock["food"].price, shop.stock["food"].quantity))
        self.assertEqual(5, shop.food_price)

    def test_a_shop_can_start_empty(self):
        shop = Shop("S", default_food=False)

        self.assertEqual({}, shop.stock)
        self.assertIsNone(shop.food_price)
        with self.assertRaises(ValueError):
            shop.food_price = 4

    def test_the_food_price_can_be_changed(self):
        shop = Shop("S", food_price=5)
        shop.food_price = 8
        self.assertEqual(8, shop.stock["food"].price)

    def test_restock_a_new_item(self):
        shop = Shop("S")
        offer = shop.restock("bread", 3, 200)

        self.assertIsInstance(offer, Offer)
        self.assertEqual(("bread", 3, 200), (offer.item_id, offer.price, offer.quantity))
        self.assertIs(offer, shop.stock["bread"])

    def test_restock_an_existing_item_replaces_the_price_and_adds_the_pieces(self):
        shop = Shop("S")
        shop.restock("bread", 3, 200)
        shop.restock("bread", 4, 50)

        self.assertEqual((4, 250), (shop.stock["bread"].price, shop.stock["bread"].quantity))

    def test_restocking_the_plain_food_keeps_it_unlimited(self):
        shop = Shop("S", food_price=5)
        shop.restock("food", 8, 100)
        self.assertEqual((8, math.inf), (shop.stock["food"].price, shop.stock["food"].quantity))

    def test_every_shop_has_its_own_stock(self):
        first, second = Shop("A"), Shop("B")
        first.restock("bread", 3, 10)
        self.assertNotIn("bread", second.stock)


class TestSelling(unittest.TestCase):

    def setUp(self):
        self.town, self.shop, self.person = make_shopper(money=20)
        self.shop.restock("bread", 3, 4)

    def test_a_sale(self):
        self.assertEqual(2, self.shop.sell(self.person, "bread", 2))

        self.assertEqual(14, self.person.money())
        self.assertEqual(2, self.person.inventory["bread"])
        self.assertEqual(2, self.shop.stock["bread"].quantity)
        self.assertEqual((6, 2), (self.shop.revenue, self.shop.sold))

    def test_limited_by_the_stock(self):
        self.assertEqual(4, self.shop.sell(self.person, "bread", 10))
        self.assertEqual(0, self.shop.stock["bread"].quantity)
        self.assertEqual(0, self.shop.sell(self.person, "bread", 1))      # sold out

    def test_limited_by_the_money(self):
        self.assertEqual(4, self.shop.sell(self.person, "food", 10))      # 20 money, 5 each
        self.assertEqual(0, self.person.money())
        self.assertEqual(0, self.shop.sell(self.person, "bread", 1))

    def test_unknown_item_and_nonsense_amounts(self):
        self.assertEqual(0, self.shop.sell(self.person, "caviar", 1))
        self.assertEqual(0, self.shop.sell(self.person, "bread", 0))
        self.assertEqual(0, self.shop.sell(self.person, "bread", -2))
        self.assertEqual(20, self.person.money())

    def test_free_items(self):
        self.shop.restock("gift", 0, 5)
        self.assertEqual(3, self.shop.sell(self.person, "gift", 3))
        self.assertEqual(20, self.person.money())

    def test_infinite_money_and_infinite_stock(self):
        self.person.attributes += Stats(money=math.inf)
        self.assertEqual(100, self.shop.sell(self.person, "food", 100))
        self.assertEqual(math.inf, self.person.money())
        self.assertEqual(math.inf, self.shop.stock["food"].quantity)

    def test_sell_food_is_selling_the_plain_food(self):
        self.assertEqual(2, self.shop.sell_food(self.person, 2))
        self.assertEqual(2, self.person.inventory["food"])
        self.assertEqual(10, self.person.money())


class TestBuyingSeveralKinds(unittest.TestCase):

    def test_the_best_value_comes_first(self):
        # food: 1 hunger for 5 (0.2 per money), bread: 2 for 3 (0.67 per money)
        town, shop, person = make_shopper(money=100)
        shop.restock("bread", 3, 100)

        self.assertEqual(FOOD_STOCK_TARGET, person.buy_food())

        self.assertEqual(FOOD_STOCK_TARGET, person.inventory["bread"])
        self.assertEqual(0, person.inventory["food"])
        self.assertEqual(100 - 3 * FOOD_STOCK_TARGET, person.money())

    def test_the_next_best_one_fills_up_when_the_best_runs_out(self):
        town, shop, person = make_shopper(money=100)
        shop.restock("bread", 3, 1)

        self.assertEqual(3, person.buy_food())
        self.assertEqual((1, 2), (person.inventory["bread"], person.inventory["food"]))
        self.assertEqual(100 - 3 - 10, person.money())

    def test_a_poor_sim_buys_what_he_can_afford(self):
        town, shop, person = make_shopper(money=4)
        shop.restock("bread", 3, 100)

        self.assertEqual(1, person.buy_food())
        self.assertEqual(1, person.inventory["bread"])
        self.assertEqual(1, person.money())

    def test_too_expensive_best_value_is_skipped(self):
        town, shop, person = make_shopper(money=10)
        shop.restock("feast", 50, 10)
        town.catalog.add(ItemDef("feast", "Feast", "food", {"hunger": -100}))      # best value of all, but 50 money

        self.assertEqual(2, person.buy_food())
        self.assertEqual(2, person.inventory["food"])
        self.assertEqual(0, person.inventory.get("feast", 0))

    def test_nothing_affordable_nothing_bought(self):
        town, shop, person = make_shopper(money=2)
        shop.restock("bread", 3, 100)
        self.assertEqual(0, person.buy_food())

    def test_free_food_is_the_best_value(self):
        town, shop, person = make_shopper(money=100)
        shop.restock("bread", 3, 100)
        shop.restock("manna", 0, 100)
        town.catalog.add(ItemDef("manna", "Manna", "food", {"hunger": -1}))

        person.buy_food()
        self.assertEqual(FOOD_STOCK_TARGET, person.inventory["manna"])
        self.assertEqual(100, person.money())

    def test_same_value_the_bigger_relief_first(self):
        town, shop, person = make_shopper(money=1000)
        shop.restock("big", 10, 100)             # 2 per 10 = 0.2, like the plain food (1 per 5)
        town.catalog.add(ItemDef("big", "Big", "food", {"hunger": -2}))

        person.buy_food()
        self.assertEqual(FOOD_STOCK_TARGET, person.inventory["big"])

    def test_what_is_already_in_the_inventory_counts(self):
        town, shop, person = make_shopper(money=100)
        shop.restock("bread", 3, 100)
        person.inventory["bread"] = 2
        person.inventory["food"] = 0

        self.assertEqual(1, person.buy_food())
        self.assertEqual(3, person.food_count())

    def test_a_full_inventory_buys_nothing(self):
        town, shop, person = make_shopper(money=100)
        person.inventory["food"] = FOOD_STOCK_TARGET
        self.assertEqual(0, person.buy_food())

    def test_things_that_do_not_fill_the_stomach_are_not_bought(self):
        town, shop, person = make_shopper(money=100, items=())
        shop.stock.clear()
        shop.restock("tonic", 1, 100)
        shop.restock("ghost", 1, 100)
        town.catalog.add(ItemDef("tonic", "Tonic", "food", {"health": 5}))     # no hunger relief
        # "ghost" is not in the catalog at all

        self.assertEqual(0, person.buy_food())

    def test_an_empty_shop_sells_nothing(self):
        town, shop, person = make_shopper(money=100, shop=Shop("Empty", default_food=False))
        self.assertEqual(0, person.buy_food())

    def test_the_books_and_the_notes_tell_what_was_bought(self):
        town, shop, person = make_shopper(money=100)
        shop.restock("bread", 3, 1)
        person.buy_food()

        self.assertEqual(3, person.totals["food_bought"])
        self.assertEqual(3 + 10, person.totals["money_spent"])
        self.assertEqual(3, town.ledger.today["food_bought"])
        self.assertEqual(13, town.ledger.today["money_spent"])
        texts = [text for _, _, text in person.log]
        self.assertIn("bought 1 Bread for 3", texts)
        self.assertIn("bought 2 food for 10", texts)

    def test_only_in_the_shop(self):
        town, shop, person = make_shopper(money=100)
        at_home(person)
        self.assertEqual(0, person.buy_food())


class TestEatingSeveralKinds(unittest.TestCase):

    def setUp(self):
        self.town, self.shop, self.person = make_shopper(money=0)
        at_home(self.person)

    def hungry(self, amount):
        self.person.attributes += Stats(hunger=amount)

    def test_the_biggest_relief_that_is_not_wasted_goes_first(self):
        self.person.inventory.update({"bread": 2, "food": 2})
        self.hungry(3)

        self.assertEqual(2, self.person.eat())        # bread (-2) first, then food (-1)

        self.assertEqual(0, self.person.attributes.hunger)
        self.assertEqual((1, 1), (self.person.inventory["bread"], self.person.inventory["food"]))

    def test_the_smallest_if_everything_is_more_than_needed(self):
        self.person.inventory.update({"bread": 1, "cake": 1})
        self.hungry(1)

        self.assertEqual(1, self.person.eat())
        self.assertEqual((0, 1), (self.person.inventory["bread"], self.person.inventory["cake"]))
        self.assertEqual(0, self.person.attributes.hunger)

    def test_a_big_meal_for_a_big_hunger(self):
        self.person.inventory.update({"bread": 1, "cake": 1, "food": 1})
        self.hungry(6)

        self.assertEqual(3, self.person.eat())
        self.assertEqual(0, self.person.attributes.hunger)

    def test_eating_stops_when_the_food_is_gone(self):
        self.person.inventory.update({"bread": 1})
        self.hungry(6)

        self.assertEqual(1, self.person.eat())
        self.assertEqual(4, self.person.attributes.hunger)

    def test_other_effects_work_too(self):
        self.person.inventory.update({"cake": 1})
        self.person.attributes.health = 5
        self.hungry(3)

        self.person.eat()
        self.assertEqual(7, self.person.attributes.health)
        self.assertEqual(0, self.person.attributes.hunger)

    def test_effects_stay_inside_the_limits(self):
        self.person.inventory.update({"cake": 1})
        self.hungry(3)                          # health is 10 of 10 already
        self.person.eat()
        self.assertEqual(10, self.person.attributes.health)

    def test_negative_effects_hurt(self):
        self.town.catalog.add(ItemDef("chili", "Chili", "food", {"hunger": -2, "stamina": -4}))
        self.person.inventory.update({"chili": 1})
        self.hungry(2)

        self.person.eat()
        self.assertEqual(6, self.person.attributes.stamina)

    def test_no_hunger_no_meal(self):
        self.person.inventory.update({"bread": 3})
        self.assertEqual(0, self.person.eat())
        self.assertEqual(3, self.person.inventory["bread"])

    def test_things_without_hunger_relief_stay_in_the_bag(self):
        self.town.catalog.add(ItemDef("tonic", "Tonic", "food", {"health": 5}))
        self.person.inventory.update({"tonic": 2})
        self.hungry(3)

        self.assertEqual(0, self.person.eat())
        self.assertEqual(2, self.person.inventory["tonic"])

    def test_unknown_items_are_ignored(self):
        self.person.inventory.update({"mystery": 5})
        self.hungry(3)
        self.assertEqual(0, self.person.eat())

    def test_only_at_home(self):
        self.person.inventory.update({"bread": 3})
        self.hungry(3)
        self.person.go(self.shop)
        self.assertEqual(0, self.person.eat())

    def test_the_books_and_the_notes(self):
        self.person.inventory.update({"bread": 2, "food": 2})
        self.hungry(3)
        self.person.eat()

        self.assertEqual(2, self.person.totals["food_eaten"])
        self.assertEqual(2, self.town.ledger.today["food_eaten"])
        texts = [text for _, _, text in self.person.log]
        self.assertIn("ate 1 Bread", texts)
        self.assertIn("ate 1 food", texts)

    def test_food_count(self):
        self.person.inventory.update({"bread": 2, "food": 1, "cake": 0, "mystery": 7})
        self.assertEqual(3, self.person.food_count())

    def test_a_sim_without_a_town_knows_the_plain_food(self):
        loner = Person(name="Loner")
        loner.inventory["food"] = 2
        self.assertEqual(2, loner.food_count())


class TestInTheTown(unittest.TestCase):

    def make_town(self, default_food=True, adult=True):
        town = TownHall("T")
        shop = Shop("Shop", work_places=3, food_price=5, default_food=default_food)
        town.add_building(shop)
        town.add_building(WorkBuilding("Job", work_places=5))
        town.add_building(MegaBuilding("Homes", stories=1, persons_per_unit=10, health=1, stamina=2, hunger=0, money=0))
        town.catalog.add(BREAD)

        people = []
        for number in range(3):
            person = Person(name=f"P{number}", age=25 if adult else 5, routine=1 + number)
            town.add_citizen(person)
            person.find_place_to_live(town.list_of_buildings())
            if adult:
                town.integrate_adult(person)
            people.append(person)
        return town, shop, people

    def test_the_bread_is_bought_first_and_eaten(self):
        town, shop, people = self.make_town()
        shop.restock("bread", 3, 1000)
        sim = Simulation(town)

        sim.run(5)

        self.assertLess(shop.stock["bread"].quantity, 1000)
        self.assertTrue(any(p.totals["food_eaten"] > 0 for p in people))
        self.assertTrue(all(p.alive for p in people))
        texts = {text for p in people for _, _, text in p.log}
        self.assertTrue(any("Bread" in text for text in texts))
        # while there is bread nobody bothers with the plain food
        self.assertEqual(0, sum(p.inventory["food"] for p in people))

    def test_when_the_good_stuff_runs_out_they_buy_the_plain_food(self):
        town, shop, people = self.make_town()
        shop.restock("bread", 3, 4)
        sim = Simulation(town)

        sim.run(20)

        self.assertEqual(0, shop.stock["bread"].quantity)
        self.assertTrue(all(p.alive for p in people))
        self.assertGreater(shop.sold, 4)

    def test_nobody_in_a_town_with_an_empty_shop_can_eat(self):
        town, shop, people = self.make_town(default_food=False)
        sim = Simulation(town)

        sim.run(10)

        self.assertEqual(3, sim.deaths)
        self.assertEqual({"starvation"}, {grave.cause for grave in town.graveyard})

    def test_the_first_items_save_a_town_with_an_empty_shop(self):
        town, shop, people = self.make_town(default_food=False)
        sim = Simulation(town)
        sim.run(5)
        shop.restock("bread", 3, 1000)                  # the first items arrive
        sim.run(30)

        self.assertTrue(all(p.alive for p in people))

    def test_children_do_not_care_about_an_empty_shop(self):
        town, shop, people = self.make_town(default_food=False, adult=False)
        sim = Simulation(town)
        sim.run(15)
        self.assertTrue(all(p.alive for p in people))

    def test_stock_catalog_and_inventories_survive_saving(self):
        town, shop, people = self.make_town()
        shop.restock("bread", 3, 1000)
        sim = Simulation(town)
        sim.run(3)

        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        loaded_shop = loaded.town_hall.shop_buildings[0]
        self.assertEqual(shop.stock["bread"].quantity, loaded_shop.stock["bread"].quantity)
        self.assertEqual(math.inf, loaded_shop.stock["food"].quantity)
        self.assertEqual(BREAD, loaded.town_hall.catalog.get("bread"))
        for before, after in zip(people, loaded.town_hall.citizens):
            self.assertEqual(before.inventory, after.inventory)
            self.assertIs(loaded.town_hall.catalog, after.catalog)

        sim.run(3)
        loaded.run(3)
        self.assertEqual(sim.totals(), loaded.totals())


if __name__ == "__main__":
    unittest.main()
