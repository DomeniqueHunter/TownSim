"""
Items that come in bulk: a delivery is counted in units (litres), the shop splits it into pieces
(bottles) that sims can buy. Nothing is created: every unit that is delivered is on the shelf,
in the pocket of a sim, or eaten.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

import console
import queries
from buildings import MegaBuilding, WorkBuilding, Shop
from buildings.shop import Offer
from itemfeed import apply_specs, ItemFeed
from items import parse_document, ItemDef, Catalog, UNIT_MAX
from persistence import save_state, load_state
from person import Person, ADULT_AGE
from services import TownHall
from simulation import Simulation
from stats import Stats

from townhelper import make_sim


MILK = {"id": "milk", "name": "Milk bottle", "category": "food", "price": 2, "unit": "l", "portion": 1,
        "stock": 1_000_000, "effects": {"hunger": -2, "health": 1}}


def document(*items):
    return json.dumps({"format": 1, "items": list(items) or [dict(MILK)]})


def errors_of(text):
    specs, errors = parse_document(text)
    assert specs == [] and errors
    return errors


class TestTheFormat(unittest.TestCase):

    def test_a_tanker_of_milk(self):
        specs, errors = parse_document(document())
        self.assertEqual([], errors)
        spec = specs[0]
        self.assertEqual(("l", 1, 1_000_000), (spec.unit, spec.portion, spec.stock))

    def test_without_unit_and_portion_it_is_one_piece_per_unit(self):
        item = {k: v for k, v in MILK.items() if k not in ("unit", "portion")}
        spec = parse_document(document(item))[0][0]
        self.assertEqual(("piece", 1), (spec.unit, spec.portion))

    def test_the_definition_carries_unit_and_portion(self):
        spec = parse_document(document(dict(MILK, unit="ml", portion=500)))[0][0]
        self.assertEqual(ItemDef("milk", "Milk bottle", "food", {"hunger": -2, "health": 1}, "", "ml", 500), spec.definition())

    def test_the_plain_food_is_one_piece_per_unit(self):
        food = Catalog().get("food")
        self.assertEqual(("piece", 1), (food.unit, food.portion))

    def test_bad_portions(self):
        for bad, shown in ((0, "0"), (-1, "-1"), (1.5, "1.5"), ("1", '"1"'), (True, "true"), (None, "null")):
            with self.subTest(portion=bad):
                self.assertEqual([f"items[0].portion: must be a whole number >= 1, got {shown}"],
                                 errors_of(document(dict(MILK, portion=bad))))

    def test_bad_units(self):
        for bad in ("", "   ", 5, "x" * (UNIT_MAX + 1)):
            with self.subTest(unit=bad):
                errors = errors_of(document(dict(MILK, unit=bad)))
                self.assertEqual(1, len(errors))
                self.assertIn(f"items[0].unit: must be text with 1 to {UNIT_MAX} characters", errors[0])
        self.assertEqual([], parse_document(document(dict(MILK, unit="x" * UNIT_MAX)))[1])

    def test_the_unit_is_trimmed(self):
        self.assertEqual("l", parse_document(document(dict(MILK, unit="  l ")))[0][0].unit)

    def test_typos_get_a_hint(self):
        self.assertEqual(['items[0].portin: unknown field (did you mean "portion"?)'],
                         errors_of(document(dict(MILK, portin=2))))
        self.assertEqual(['items[0].units: unknown field (did you mean "unit"?)'],
                         errors_of(document(dict(MILK, units="l"))))

    def test_huge_deliveries_are_fine(self):
        specs, errors = parse_document(document(dict(MILK, stock=10 ** 15)))
        self.assertEqual([], errors)
        self.assertEqual(10 ** 15, specs[0].stock)


class TestTheShelf(unittest.TestCase):

    def test_a_delivery_is_one_number_not_a_million_things(self):
        shop = Shop("S")
        offer = shop.restock("milk", 2, 1_000_000)

        self.assertEqual(1_000_000, offer.quantity)
        self.assertEqual(1_000_000, offer.units)
        self.assertEqual(2, len(shop.stock))             # the plain food and the milk
        shop.restock("milk", 2, 10 ** 15)                # a tanker of tankers costs nothing either
        self.assertEqual(10 ** 15 + 1_000_000, shop.stock["milk"].units)

    def test_the_delivery_is_split_into_pieces(self):
        shop = Shop("S")
        offer = shop.restock("juice", 4, 10, portion=3)
        self.assertEqual((3, 1, 3, 10), (offer.quantity, offer.loose, offer.portion, offer.units))

    def test_what_is_left_over_waits_for_the_next_delivery(self):
        shop = Shop("S")
        shop.restock("juice", 4, 10, portion=3)         # 3 pieces and 1 loose
        offer = shop.restock("juice", 4, 5, portion=3)  # 6 units loose: 2 more pieces
        self.assertEqual((5, 0, 15), (offer.quantity, offer.loose, offer.units))
        offer = shop.restock("juice", 4, 2, portion=3)
        self.assertEqual((5, 2, 17), (offer.quantity, offer.loose, offer.units))

    def test_the_portion_cannot_change(self):
        shop = Shop("S")
        shop.restock("juice", 4, 10, portion=3)
        with self.assertRaisesRegex(ValueError, "pieces of 3 units here, not 5"):
            shop.restock("juice", 4, 10, portion=5)
        self.assertEqual((3, 1), (shop.stock["juice"].quantity, shop.stock["juice"].loose))

    def test_the_price_is_per_piece_and_is_replaced(self):
        shop = Shop("S")
        shop.restock("milk", 2, 100)
        shop.restock("milk", 3, 100)
        self.assertEqual(3, shop.stock["milk"].price)

    def test_a_shelf_that_never_runs_out_stays_that_way(self):
        shop = Shop("S", food_price=5)
        shop.restock("food", 6, 1000)
        offer = shop.stock["food"]
        self.assertEqual((math.inf, 0, math.inf), (offer.quantity, offer.loose, offer.units))

    def test_an_offer_made_by_hand_is_still_the_old_thing(self):
        offer = Offer("bread", 3, 200)
        self.assertEqual((200, 1, 0, 200), (offer.quantity, offer.portion, offer.loose, offer.units))

    def test_selling_takes_whole_pieces(self):
        shop = Shop("S")
        shop.restock("juice", 1, 10, portion=3)         # 3 pieces and 1 loose
        buyer = Person(name="Buyer")
        buyer.attributes += Stats(money=100)

        self.assertEqual(2, shop.sell(buyer, "juice", 2))
        offer = shop.stock["juice"]
        self.assertEqual((1, 1, 4), (offer.quantity, offer.loose, offer.units))
        self.assertEqual(2, buyer.inventory["juice"])

        self.assertEqual(1, shop.sell(buyer, "juice", 5))        # only one piece is left
        self.assertEqual((0, 1, 1), (offer.quantity, offer.loose, offer.units))
        self.assertEqual(0, shop.sell(buyer, "juice", 1))        # one loose unit is no piece
        self.assertEqual(3, buyer.inventory["juice"])


class TestApplyingDeliveries(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.shop = self.sim.town_hall.shop_buildings[0]

    def apply(self, *items):
        specs, errors = parse_document(document(*items))
        self.assertEqual([], errors)
        return apply_specs(self.sim, specs)

    def test_a_tanker_of_milk(self):
        messages, errors = self.apply(MILK)

        self.assertEqual([], errors)
        self.assertEqual(["Milk bottle: +1000000 l = 1000000 pieces of 1 l at Shop (price 2 per piece)"], messages)
        offer = self.shop.stock["milk"]
        self.assertEqual((1_000_000, 2, 1), (offer.quantity, offer.price, offer.portion))
        self.assertEqual(("l", 1), (self.sim.town_hall.catalog.get("milk").unit, self.sim.town_hall.catalog.get("milk").portion))

    def test_bigger_pieces_and_a_rest(self):
        messages, _ = self.apply(dict(MILK, id="juice", name="Juice", unit="ml", portion=250, stock=1000, price=3))
        self.assertEqual(["Juice: +1000 ml = 4 pieces of 250 ml at Shop (price 3 per piece)"], messages)

        messages, _ = self.apply(dict(MILK, id="cream", name="Cream", unit="ml", portion=300, stock=1000))
        self.assertEqual(["Cream: +1000 ml = 3 pieces of 300 ml at Shop (price 2 per piece)"], messages)
        self.assertEqual(100, self.shop.stock["cream"].loose)

        # the 100 ml that were left over and the new 1000 ml make 1100 ml: 3 more pieces and 200 ml left over
        messages, _ = self.apply(dict(MILK, id="cream", name="Cream", unit="ml", portion=300, stock=1000))
        self.assertEqual(["Cream: +1000 ml = 3 pieces of 300 ml at Shop (price 2 per piece)"], messages)
        self.assertEqual((6, 200), (self.shop.stock["cream"].quantity, self.shop.stock["cream"].loose))

    def test_the_next_tanker_adds_to_the_first(self):
        self.apply(MILK)
        self.apply(dict(MILK, price=3))
        offer = self.shop.stock["milk"]
        self.assertEqual((2_000_000, 3), (offer.quantity, offer.price))

    def test_a_new_price_without_a_delivery(self):
        self.apply(MILK)
        messages, _ = self.apply(dict(MILK, price=9, stock=0))
        self.assertEqual(["Milk bottle: price at Shop is now 9"], messages)

    def test_unit_and_portion_must_stay_the_same_everywhere(self):
        self.apply(MILK)
        for change in ({"portion": 2}, {"unit": "kg"}, {"unit": "ml", "portion": 1000}):
            with self.subTest(change=change):
                _, errors = self.apply(dict(MILK, **change))
                self.assertEqual(1, len(errors))
                self.assertIn('items[0]: "milk" already exists as a food', errors[0])
                self.assertIn("1 l per piece, a new file must keep category, effects, unit and portion", errors[0])
        self.assertEqual(1_000_000, self.shop.stock["milk"].quantity)

    def test_the_plain_food_cannot_get_other_pieces(self):
        plain = {"id": "food", "name": "food", "category": "food", "price": 5, "stock": 0, "effects": {"hunger": -1},
                 "portion": 2}
        _, errors = self.apply(plain)
        self.assertEqual(1, len(errors))

    def test_all_or_nothing_also_for_the_portion(self):
        self.apply(MILK)
        _, errors = self.apply(dict(MILK, id="cream", name="Cream"), dict(MILK, portion=3))
        self.assertEqual(1, len(errors))
        self.assertNotIn("cream", self.shop.stock)

    def test_a_gift_of_whole_pieces(self):
        maxima = next(p for p in self.sim.town_hall.citizens if p.name == "Maxima")
        messages, errors = self.apply(dict(MILK, id="juice", name="Juice", unit="ml", portion=250, stock=1000,
                                           price=0, deliver_to="Maxima"))

        self.assertEqual([], errors)
        self.assertEqual(["Juice: 4 pieces (1000 ml) given to Maxima"], messages)
        self.assertEqual(4, maxima.inventory["juice"])
        self.assertIn("received 4 Juice as a gift", maxima.log[-1][2])

    def test_a_gift_must_be_whole_pieces(self):
        for stock in (1001, 249, 0):
            with self.subTest(stock=stock):
                _, errors = self.apply(dict(MILK, id="juice", unit="ml", portion=250, stock=stock, price=0,
                                            deliver_to="Maxima"))
                self.assertEqual(["items[0].stock: must be a whole number of pieces (250 ml each), at least one, "
                                  "when the item is given to a sim"], errors)

    def test_a_gift_of_single_pieces_keeps_its_old_message(self):
        _, errors = self.apply(dict(MILK, stock=0, deliver_to="Maxima"))
        self.assertEqual(["items[0].stock: must be at least 1 when the item is given to a sim"], errors)

    def test_through_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "milk.json").write_text(document())
            lines = []
            feed = ItemFeed(folder, log=lines.append, stable_seconds=0, min_interval=0)
            feed.poll(self.sim)
            self.assertEqual(1, feed.poll(self.sim))
            feed.finish()

            self.assertEqual(1_000_000, self.shop.stock["milk"].quantity)
            self.assertTrue(any("1000000 pieces of 1 l" in line for line in lines))
            self.assertEqual(1, len(list(folder.glob("_consumed_milk_*.json"))))


def make_town(default_food=False, workers=3):
    town = TownHall("T")
    shop = Shop("Shop", work_places=3, food_price=5, default_food=default_food)
    town.add_building(shop)
    town.add_building(WorkBuilding("Job", work_places=5))
    town.add_building(MegaBuilding("Homes", stories=1, persons_per_unit=10, health=1, stamina=2, hunger=0, money=0))
    people = []
    for number in range(workers):
        person = Person(name=f"P{number}", age=25, routine=1 + number)
        town.add_citizen(person)
        person.find_place_to_live(town.list_of_buildings())
        town.integrate_adult(person)
        people.append(person)
    return town, shop, people


class TestNothingIsCreated(unittest.TestCase):
    """every litre that is delivered is on the shelf, in a pocket or eaten"""

    def check(self, delivered, portion, cycles):
        town, shop, people = make_town()
        town.catalog.add(ItemDef("milk", "Milk bottle", "food", {"hunger": -2}, "", "l", portion))
        shop.restock("milk", 1, delivered, portion)
        sim = Simulation(town)

        sim.run(cycles)

        offer = shop.stock["milk"]
        in_pockets = sum(p.inventory.get("milk", 0) for p in people) * portion
        eaten = sum(p.totals["food_eaten"] for p in people) * portion
        self.assertTrue(all(p.alive for p in people))
        self.assertGreater(eaten, 0)
        self.assertEqual(delivered, offer.units + in_pockets + eaten)
        return offer, in_pockets, eaten

    def test_in_bottles_of_one_litre(self):
        offer, in_pockets, eaten = self.check(500, 1, 6)
        self.assertGreater(in_pockets, 0)

    def test_in_bigger_pieces_with_a_rest(self):
        offer, _, _ = self.check(1000, 3, 6)            # 333 pieces and 1 litre that nobody can buy
        self.assertEqual(1, offer.loose)
        self.assertGreater(offer.quantity, 0)

    def test_until_it_runs_out(self):
        offer, in_pockets, eaten = self.check(15, 1, 8)      # 3 sims eat about 3 pieces a day
        self.assertEqual(0, offer.quantity)
        self.assertEqual(15, in_pockets + eaten)        # all of it is with the sims, nothing disappeared

    def test_without_a_delivery_nobody_can_eat(self):
        town, shop, people = make_town()                # no plain food, nothing delivered
        sim = Simulation(town)
        sim.run(10)
        self.assertEqual(3, sim.deaths)


class TestShowingBulk(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(1)
        specs, _ = parse_document(document(MILK, dict(MILK, id="juice", name="Juice", unit="ml", portion=250,
                                                      stock=1100, price=3)))
        apply_specs(self.sim, specs)

    def ask(self, cmd, *args):
        return queries.run(self.sim, cmd, list(args))

    def test_the_shelf_knows_unit_and_portion(self):
        stock = {entry["item"]: entry for entry in self.ask("building", "Shop")["stock"]}
        self.assertEqual((1_000_000, 1, "l", 0), (stock["milk"]["quantity"], stock["milk"]["portion"],
                                                   stock["milk"]["unit"], stock["milk"]["loose"]))
        self.assertEqual((4, 250, "ml", 100), (stock["juice"]["quantity"], stock["juice"]["portion"],
                                               stock["juice"]["unit"], stock["juice"]["loose"]))
        self.assertEqual((math.inf, 1, "piece"), (stock["food"]["quantity"], stock["food"]["portion"], stock["food"]["unit"]))

    def test_the_items_know_their_piece(self):
        items = {item["id"]: item for item in self.ask("items")["items"]}
        self.assertEqual(("l", 1), (items["milk"]["unit"], items["milk"]["portion"]))
        self.assertEqual(("ml", 250), (items["juice"]["unit"], items["juice"]["portion"]))
        self.assertEqual(100, items["juice"]["offers"][0]["loose"])

    def test_the_text_for_the_shelf(self):
        text = console.fmt_building(self.ask("building", "Shop"))
        self.assertIn("food 5 (unlimited)", text)                 # nothing new for plain pieces
        self.assertIn("milk 2 (1000000 left, 1 l each)", text)
        self.assertIn("juice 3 (4 left, 250 ml each)", text)

    def test_the_text_for_the_item_table(self):
        lines = console.fmt_items(self.ask("items")).splitlines()
        self.assertEqual("piece", lines[0].split()[4])
        milk = next(line for line in lines if line.startswith("milk"))
        self.assertRegex(milk, r"hunger -2, health \+1\s+1 l\s+Shop 2 \(1000000 left\)")
        self.assertRegex(next(line for line in lines if line.startswith("juice")), r"1 piece|250 ml")
        self.assertRegex(next(line for line in lines if line.startswith("food")), r"1 piece")

    def test_the_text_stays_plain_ascii(self):
        console.fmt_items(self.ask("items")).encode("ascii")
        console.fmt_building(self.ask("building", "Shop")).encode("ascii")
        console.fmt_goods(self.ask("goods")).encode("ascii")

    def test_everything_can_be_sent_as_json(self):
        for cmd, args in (("items", []), ("goods", []), ("building", ["Shop"])):
            with self.subTest(cmd=cmd):
                text = json.dumps(queries.run(self.sim, cmd, args))
                self.assertEqual(json.loads(text), queries.run(self.sim, cmd, args))


class TestSaving(unittest.TestCase):

    def test_a_shelf_with_a_rest_survives_saving(self):
        town, shop, people = make_town()
        town.catalog.add(ItemDef("juice", "Juice", "food", {"hunger": -2}, "", "ml", 300))
        shop.restock("juice", 1, 1000, 300)
        sim = Simulation(town)
        sim.run(3)

        with tempfile.TemporaryDirectory() as tmp:
            save_state(sim, Path(tmp) / "save.pkl")
            loaded = load_state(Path(tmp) / "save.pkl")

        before = shop.stock["juice"]
        after = loaded.town_hall.shop_buildings[0].stock["juice"]
        self.assertEqual((before.quantity, before.loose, before.portion, before.price),
                         (after.quantity, after.loose, after.portion, after.price))
        self.assertEqual(("ml", 300), (loaded.town_hall.catalog.get("juice").unit, loaded.town_hall.catalog.get("juice").portion))

        sim.run(3)
        loaded.run(3)
        self.assertEqual(shop.stock["juice"].units, loaded.town_hall.shop_buildings[0].stock["juice"].units)


if __name__ == "__main__":
    unittest.main()
