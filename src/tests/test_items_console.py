
import json
import math
import unittest

import console
import display
import queries
from client import GameClient
from gameserver import GameServer
from items import ItemDef

from townhelper import make_sim


def stocked_sim():
    """the test town, its shop sells bread and cake as well, Maxima holds a golden apple"""
    sim = make_sim()
    sim.run(2)
    town = sim.town_hall
    shop = town.shop_buildings[0]
    town.catalog.add(ItemDef("bread", "Bread", "food", {"hunger": -2}, "fresh"))
    town.catalog.add(ItemDef("cake", "Cake", "food", {"hunger": -3, "health": 2}))
    town.catalog.add(ItemDef("golden_apple", "Golden Apple", "food", {"hunger": -5}))
    shop.restock("bread", 3, 200)
    shop.restock("cake", 8, 0)                  # sold out
    maxima = next(p for p in town.citizens if p.name == "Maxima")
    maxima.inventory["golden_apple"] = 1
    maxima.inventory["bread"] = 2
    return sim, shop, maxima


class TestQueries(unittest.TestCase):

    def setUp(self):
        self.sim, self.shop, self.maxima = stocked_sim()

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_items(self):
        items = {item["id"]: item for item in self.ask("items")["items"]}

        self.assertEqual({"food", "bread", "cake", "golden_apple"}, set(items))
        bread = items["bread"]
        self.assertEqual(("Bread", "food", {"hunger": -2}, "fresh"),
                         (bread["name"], bread["category"], bread["effects"], bread["description"]))
        self.assertEqual([{"shop": "Shop", "price": 3, "quantity": 200, "loose": 0}], bread["offers"])
        self.assertEqual(2, bread["held"])
        self.assertEqual([], items["golden_apple"]["offers"])
        self.assertEqual(1, items["golden_apple"]["held"])
        self.assertEqual(0, items["cake"]["offers"][0]["quantity"])

    def test_the_plain_food_is_unlimited_and_held_by_sims(self):
        food = next(i for i in self.ask("items")["items"] if i["id"] == "food")
        self.assertEqual(math.inf, food["offers"][0]["quantity"])
        self.assertEqual(sum(p.inventory["food"] for p in self.sim.living()), food["held"])

    def test_the_dead_hold_nothing(self):
        self.maxima.inventory["gem"] = 5
        self.sim.town_hall.catalog.add(ItemDef("gem", "Gem", "food", {"hunger": -1}))
        gem = next(i for i in self.ask("items")["items"] if i["id"] == "gem")
        self.assertEqual(5, gem["held"])

        self.maxima.alive = False
        gem = next(i for i in self.ask("items")["items"] if i["id"] == "gem")
        self.assertEqual(0, gem["held"])

    def test_a_shop_shows_its_stock(self):
        data = self.ask("building", "Shop")
        stock = {entry["item"]: entry for entry in data["stock"]}

        self.assertEqual({"food", "bread", "cake"}, set(stock))
        self.assertEqual(("Bread", 3, 200), (stock["bread"]["name"], stock["bread"]["price"], stock["bread"]["quantity"]))
        self.assertEqual(5, data["food_price"])

    def test_goods_lists_what_the_shops_sell(self):
        (shop,) = self.ask("goods")["shops"]
        self.assertEqual("Shop", shop["name"])
        self.assertEqual({"food", "bread", "cake"}, {entry["item"] for entry in shop["items"]})
        self.assertEqual(5, shop["price"])

    def test_an_empty_shop(self):
        sim = make_sim()
        shop = sim.town_hall.shop_buildings[0]
        shop.stock.clear()
        data = queries.run(sim, "building", ["Shop"])
        self.assertEqual([], data["stock"])
        self.assertIsNone(data["food_price"])

    def test_the_inventory_of_a_sim(self):
        inventory = self.ask("npc", "Maxima")["inventory"]
        self.assertEqual(2, inventory["bread"])
        self.assertEqual(1, inventory["golden_apple"])

    def test_all_answers_can_be_sent_as_json(self):
        for cmd, args in (("items", []), ("goods", []), ("building", ["Shop"]), ("npc", ["Maxima"]),
                          ("snapshot", ["Maxima"])):
            with self.subTest(cmd=cmd):
                text = json.dumps(queries.run(self.sim, cmd, args))
                self.assertEqual(json.loads(text), queries.run(self.sim, cmd, args))


class TestFormatting(unittest.TestCase):

    def test_quantity(self):
        self.assertEqual("unlimited", console.fmt_quantity(math.inf))
        self.assertEqual("200 left", console.fmt_quantity(200))
        self.assertEqual("0 left", console.fmt_quantity(0))

    def test_offers(self):
        offers = [{"item": "food", "price": 5, "quantity": math.inf}, {"item": "bread", "price": 3, "quantity": 200}]
        self.assertEqual("food 5 (unlimited), bread 3 (200 left)", console.fmt_offers(offers))
        self.assertEqual("nothing", console.fmt_offers([]))

    def test_inventory(self):
        self.assertEqual("food 0", console.fmt_inventory({"food": 0}))
        self.assertEqual("food 2, bread 1, golden_apple 3",
                         console.fmt_inventory({"golden_apple": 3, "food": 2, "bread": 1, "cake": 0}))
        self.assertEqual("food 0, bread 1", console.fmt_inventory({"bread": 1}))

    def test_effects(self):
        self.assertEqual("hunger -2, health +1", console.fmt_effects({"hunger": -2, "health": 1}))
        self.assertEqual("-", console.fmt_effects({}))


class TestConsole(unittest.TestCase):

    def setUp(self):
        self.sim, self.shop, self.maxima = stocked_sim()
        self.server = GameServer(self.sim, port=0)
        self.server.start()
        self.addCleanup(self.server.stop)
        self.client = GameClient(port=self.server.port, timeout=3)
        self.addCleanup(self.client.close)

    def out(self, *words):
        lines = []
        console.execute(self.client, list(words), out=lines.append)
        return "\n".join(lines)

    def test_items(self):
        text = self.out("items")
        lines = text.splitlines()

        self.assertEqual(["id", "name", "category", "effects", "piece", "sold", "at", "held", "by", "sims"], lines[0].split())
        self.assertEqual(5, len(lines))
        bread = next(line for line in lines if line.startswith("bread"))
        self.assertIn("Bread", bread)
        self.assertIn("hunger -2", bread)
        self.assertIn("Shop 3 (200 left)", bread)
        cake = next(line for line in lines if line.startswith("cake"))
        self.assertIn("hunger -3, health +2", cake)
        self.assertIn("Shop 8 (0 left)", cake)
        self.assertIn("Shop 5 (unlimited)", next(line for line in lines if line.startswith("food")))
        self.assertIn("nowhere", next(line for line in lines if line.startswith("golden_apple")))

    def test_a_shop_shows_what_it_has_for_sale(self):
        text = self.out("building", "Shop")
        self.assertIn("food price: 5", text)
        self.assertIn("for sale:   food 5 (unlimited), bread 3 (200 left), cake 8 (0 left)", text)

    def test_goods(self):
        text = self.out("goods")
        self.assertIn("Shop: sold ", text)
        self.assertIn("for sale: food 5 (unlimited), bread 3 (200 left), cake 8 (0 left)", text)

    def test_the_inventory_of_an_npc(self):
        text = self.out("npc", "Maxima")
        self.assertIn(f"inventory: food {self.maxima.inventory['food']}, bread 2, golden_apple 1", text)

    def test_plain_ascii(self):
        for words in (["items"], ["building", "Shop"], ["goods"], ["npc", "Maxima"]):
            with self.subTest(words=words):
                self.out(*words).encode("ascii")

    def test_help_lists_items(self):
        self.assertIn("items", self.out("help"))


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)

    def request(self, cmd, *args):
        return self.answers.pop(0)


class TestFollowCountsEverythingYouCanEat(unittest.TestCase):

    def test_status_line(self):
        data = {
            "name": "Maxima", "alive": True,
            "clock": {"day": 2, "phase": "NOON", "next_phase": "X", "cycle": 1},
            "location": {"text": "home", "kind": "home", "building": "B", "unit": 0, "address": [0, 0]},
            "action": {"type": "SLEEP", "text": "sleeping", "phase": "NOON"},
            "stats": {"money": {"value": 5, "max": 10}, "hunger": {"value": 1, "max": 10}},
            "inventory": {"food": 2, "bread": 3, "golden_apple": 1},
            "log": [],
        }
        lines = []
        console.follow(FakeClient([data]), "Maxima", out=lines.append, sleep=lambda s: None, max_updates=1)
        self.assertIn("food 6", lines[2])


class TestWindowText(unittest.TestCase):

    def test_goods_text_shows_the_offers(self):
        sim, shop, _ = stocked_sim()
        text = display.goods_text(queries.run(sim, "goods", []))
        self.assertIn("Shop: sold ", text)
        self.assertIn("for sale: food 5 (unlimited), bread 3 (200 left), cake 8 (0 left)", text)

    def test_an_empty_shop_does_not_break_the_text(self):
        sim = make_sim()
        sim.town_hall.shop_buildings[0].stock.clear()
        text = display.goods_text(queries.run(sim, "goods", []))
        self.assertIn("for sale: nothing", text)


if __name__ == "__main__":
    unittest.main()
