
import json
import unittest

from items import (parse_document, ItemSpec, ItemDef, Catalog, BUILTIN_FOOD, EFFECT_KEYS, CATEGORIES,
                   FORMAT_VERSION)


def item(**changes):
    """a valid food item, with some fields changed (None removes a field)"""
    base = {"id": "bread", "name": "Bread", "category": "food", "price": 3, "stock": 200,
            "effects": {"hunger": -2}}
    base.update(changes)
    return {key: value for key, value in base.items() if value is not None}


def document(*items, **changes):
    base = {"format": 1, "items": list(items) or [item()]}
    base.update(changes)
    return json.dumps({key: value for key, value in base.items() if value is not None})


def errors_of(text):
    specs, errors = parse_document(text)
    assert specs == [], "a file with errors must not give any item"
    assert errors, "expected errors"
    return errors


class TestValidFiles(unittest.TestCase):

    def test_a_minimal_item(self):
        specs, errors = parse_document(document())

        self.assertEqual([], errors)
        self.assertEqual([ItemSpec(id="bread", name="Bread", category="food", price=3, stock=200,
                                   effects={"hunger": -2})], specs)

    def test_every_field(self):
        specs, errors = parse_document(document(item(
            description="Fresh from the bakery.", store="Corner Shop",
            effects={"hunger": -2, "health": 1, "stamina": -1})))

        self.assertEqual([], errors)
        spec = specs[0]
        self.assertEqual("Fresh from the bakery.", spec.description)
        self.assertEqual("Corner Shop", spec.store)
        self.assertEqual({"hunger": -2, "health": 1, "stamina": -1}, spec.effects)
        self.assertIsNone(spec.deliver_to)

    def test_a_gift_for_a_sim(self):
        specs, errors = parse_document(document(item(deliver_to="Maxima", price=0, stock=1)))
        self.assertEqual([], errors)
        self.assertEqual("Maxima", specs[0].deliver_to)

    def test_several_items(self):
        specs, errors = parse_document(document(item(), item(id="cake", name="Cake")))
        self.assertEqual(["bread", "cake"], [spec.id for spec in specs])

    def test_zero_price_and_zero_stock_are_fine(self):
        specs, errors = parse_document(document(item(price=0, stock=0)))
        self.assertEqual([], errors)
        self.assertEqual((0, 0), (specs[0].price, specs[0].stock))

    def test_effects_that_are_zero_are_left_out(self):
        specs, _ = parse_document(document(item(effects={"hunger": -2, "health": 0})))
        self.assertEqual({"hunger": -2}, specs[0].effects)

    def test_texts_are_trimmed(self):
        specs, _ = parse_document(document(item(name="  Bread ", store=" Corner Shop ")))
        self.assertEqual(("Bread", "Corner Shop"), (specs[0].name, specs[0].store))

    def test_ids(self):
        for good in ("a", "bread", "golden_apple", "a-b_c1", "a" * 40):
            with self.subTest(id=good):
                self.assertEqual([], parse_document(document(item(id=good)))[1])

    def test_the_same_id_for_different_targets_is_fine(self):
        text = document(item(store="A"), item(store="B"), item(deliver_to="Maxima"), item(deliver_to="Bob"), item())
        self.assertEqual([], parse_document(text)[1])

    def test_the_format_version(self):
        self.assertEqual(1, FORMAT_VERSION)


class TestWholeFile(unittest.TestCase):

    def test_not_json(self):
        (error,) = errors_of("{ nope")
        self.assertRegex(error, r"^\(file\): not valid JSON: .+ \(line 1, column \d+\)$")

    def test_empty_file(self):
        self.assertIn("not valid JSON", errors_of("")[0])

    def test_not_an_object(self):
        for text in ("[]", "3", '"x"', "null"):
            with self.subTest(text=text):
                self.assertEqual(['(file): must be a JSON object like {"format": 1, "items": [...]}'], errors_of(text))

    def test_format(self):
        self.assertEqual(["format: is required (use 1)"], errors_of(document(format=None)))
        self.assertEqual(["format: must be 1, got 2"], errors_of(document(format=2)))
        self.assertEqual(['format: must be 1, got "1"'], errors_of(document(format="1")))
        self.assertEqual(["format: must be 1, got true"], errors_of(document(format=True)))
        self.assertEqual(["format: must be 1, got 1.0"], errors_of(document(format=1.0)))

    def test_items(self):
        self.assertEqual(["items: is required"], errors_of('{"format": 1}'))
        self.assertEqual(["items: must be a list"], errors_of('{"format": 1, "items": {}}'))
        self.assertEqual(["items: must contain at least one item"], errors_of('{"format": 1, "items": []}'))
        self.assertEqual(["items[1]: must be an object"], errors_of(f'{{"format": 1, "items": [{json.dumps(item())}, 5]}}'))

    def test_unknown_top_level_field(self):
        self.assertEqual(['itms: unknown field (did you mean "items"?)'], errors_of(document(itms=[])))

    def test_a_key_twice_in_one_object(self):
        text = '{"format": 1, "items": [{"id": "a", "id": "b"}]}'
        self.assertEqual(['(file): the key "id" appears twice in the same object'], errors_of(text))

    def test_nan_and_infinity_are_not_numbers_here(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(literal=literal):
                text = document().replace('"price": 3', f'"price": {literal}')
                self.assertIn("items[0].price: must be a whole number >= 0", errors_of(text)[0])


class TestFields(unittest.TestCase):

    def error(self, **changes):
        (error,) = errors_of(document(item(**changes)))
        return error

    def test_required_fields(self):
        for field in ("id", "name", "category", "price", "stock"):
            with self.subTest(field=field):
                self.assertEqual(f"items[0].{field}: is required", self.error(**{field: None}))

    def test_bad_ids(self):
        for bad in ("Bread!", "Bread", "1abc", "a b", "", "a" * 41, "-a", "_a", "ä"):
            with self.subTest(id=bad):
                self.assertIn("items[0].id: must start with a lowercase letter", self.error(id=bad))
        self.assertIn('got "Bread!"', self.error(id="Bread!"))
        self.assertIn("got 5", self.error(id=5))

    def test_bad_names(self):
        for bad in ("", "   ", "x" * 61, 5):
            with self.subTest(name=bad):
                self.assertIn("items[0].name: must be text with 1 to 60 characters", self.error(name=bad))
        self.assertEqual([], parse_document(document(item(name="x" * 60)))[1])

    def test_unknown_category(self):
        self.assertEqual('items[0].category: must be one of: food, got "toy"', self.error(category="toy"))
        self.assertEqual("items[0].category: must be one of: food, got 5", self.error(category=5))

    def test_prices_and_stock_must_be_whole_numbers(self):
        for field in ("price", "stock"):
            for bad, shown in (("3", '"3"'), (1.5, "1.5"), (3.0, "3.0"), (True, "true"), (-1, "-1")):
                with self.subTest(field=field, value=bad):
                    self.assertEqual(f"items[0].{field}: must be a whole number >= 0, got {shown}",
                                     self.error(**{field: bad}))

    def test_description_must_be_text(self):
        self.assertEqual("items[0].description: must be text, got 5", self.error(description=5))

    def test_store_and_deliver_to_must_be_names(self):
        self.assertEqual('items[0].store: must be a name (text), got ""', self.error(store=""))
        self.assertEqual("items[0].store: must be a name (text), got 5", self.error(store=5))
        self.assertEqual('items[0].deliver_to: must be a name (text), got "  "', self.error(deliver_to="  "))

    def test_store_and_deliver_to_exclude_each_other(self):
        self.assertEqual('items[0]: use either "store" or "deliver_to", not both',
                         self.error(store="Shop", deliver_to="Maxima"))

    def test_typos_get_a_hint(self):
        self.assertEqual('items[0].pirce: unknown field (did you mean "price"?)', self.error(pirce=3))
        self.assertEqual('items[0].stok: unknown field (did you mean "stock"?)', self.error(stok=3))

    def test_unknown_fields_without_a_close_match(self):
        message = self.error(color="red")
        self.assertTrue(message.startswith("items[0].color: unknown field (allowed: id, name, category, "), message)
        self.assertIn("effects", message)

    def test_a_typo_in_a_required_field_gives_both_problems(self):
        errors = errors_of(document(item(pirce=3, price=None)))
        self.assertEqual(['items[0].pirce: unknown field (did you mean "price"?)', "items[0].price: is required"], errors)


class TestFoodEffects(unittest.TestCase):

    def errors(self, effects):
        return errors_of(document(item(effects=effects)))

    def test_effects_are_required_for_food(self):
        self.assertEqual(["items[0].effects: is required for food"], errors_of(document(item(effects=None))))

    def test_effects_must_be_an_object(self):
        self.assertEqual(['items[0].effects: must be an object like {"hunger": -2}, got 5'], self.errors(5))
        self.assertEqual(['items[0].effects: must be an object like {"hunger": -2}, got [-2]'], self.errors([-2]))

    def test_unknown_effect(self):
        self.assertEqual(["items[0].effects.speed: unknown effect (allowed: health, stamina, hunger)"],
                         self.errors({"hunger": -2, "speed": 1}))
        self.assertEqual(['items[0].effects.hungr: unknown effect (did you mean "hunger"?)'],
                         self.errors({"hungr": -2}))

    def test_effects_are_whole_numbers(self):
        self.assertEqual(["items[0].effects.hunger: must be a whole number, got 1.5"], self.errors({"hunger": 1.5}))
        self.assertEqual(['items[0].effects.health: must be a whole number, got "2"'], self.errors({"hunger": -1, "health": "2"}))
        self.assertEqual(["items[0].effects.health: must be a whole number, got true"], self.errors({"hunger": -1, "health": True}))

    def test_a_food_has_to_lower_hunger(self):
        self.assertEqual(['items[0].effects: a food has to lower hunger, add "hunger" with a negative number like -2'],
                         self.errors({"health": 3}))
        self.assertEqual(['items[0].effects: a food has to lower hunger, add "hunger" with a negative number like -2'],
                         self.errors({}))
        self.assertEqual(["items[0].effects.hunger: a food has to lower hunger, use a negative number like -2 (got 0)"],
                         self.errors({"hunger": 0}))
        self.assertEqual(["items[0].effects.hunger: a food has to lower hunger, use a negative number like -2 (got 3)"],
                         self.errors({"hunger": 3}))

    def test_health_and_stamina_may_be_negative(self):
        specs, errors = parse_document(document(item(effects={"hunger": -3, "health": -1, "stamina": -2})))
        self.assertEqual([], errors)

    def test_effect_keys_and_categories_known_to_the_checker(self):
        self.assertEqual(("health", "stamina", "hunger"), EFFECT_KEYS)
        self.assertEqual(("food",), CATEGORIES)


class TestSeveralProblems(unittest.TestCase):

    def test_all_problems_of_all_items_are_reported_together(self):
        text = document(
            item(id="Bad!", price="3", pirce=1),
            item(id="ok"),
            item(id="third", stock=-1, effects={"hunger": 1}),
        )
        errors = errors_of(text)

        self.assertEqual(5, len(errors))
        self.assertTrue(any(e.startswith("items[0].id:") for e in errors))
        self.assertTrue(any(e.startswith("items[0].price:") for e in errors))
        self.assertTrue(any(e.startswith("items[0].pirce:") for e in errors))
        self.assertTrue(any(e.startswith("items[2].stock:") for e in errors))
        self.assertTrue(any(e.startswith("items[2].effects.hunger:") for e in errors))
        self.assertFalse(any(e.startswith("items[1]") for e in errors))

    def test_one_bad_item_means_no_item_at_all(self):
        specs, errors = parse_document(document(item(), item(id="cake", price="x")))
        self.assertEqual([], specs)
        self.assertEqual(1, len(errors))

    def test_listed_twice_for_the_same_target(self):
        errors = errors_of(document(item(), item(price=4)))
        self.assertEqual(['items[1].id: "bread" is listed twice for the same target (first at items[0])'], errors)

    def test_listed_twice_for_the_same_shop_in_another_spelling(self):
        errors = errors_of(document(item(store="Corner Shop"), item(store="corner shop")))
        self.assertEqual(1, len(errors))
        self.assertIn("is listed twice", errors[0])

    def test_default_shop_and_named_shop_are_different_targets(self):
        self.assertEqual([], parse_document(document(item(), item(store="Corner Shop")))[1])


class TestCatalogAndDefinitions(unittest.TestCase):

    def test_the_catalog_starts_with_the_plain_food(self):
        catalog = Catalog()
        self.assertIn("food", catalog)
        self.assertIs(BUILTIN_FOOD, catalog.get("food"))
        self.assertEqual({"hunger": -1}, catalog.get("food").effects)
        self.assertEqual(1, len(catalog))

    def test_add_and_replace(self):
        catalog = Catalog()
        catalog.add(ItemDef("bread", "Bread", "food", {"hunger": -2}))
        catalog.add(ItemDef("bread", "Fine Bread", "food", {"hunger": -2}))

        self.assertEqual("Fine Bread", catalog.get("bread").name)
        self.assertEqual(2, len(catalog))
        self.assertEqual({"food", "bread"}, {item.id for item in catalog})
        self.assertIsNone(catalog.get("nothing"))

    def test_every_catalog_has_its_own_items_dict(self):
        first, second = Catalog(), Catalog()
        first.add(ItemDef("bread", "Bread", "food", {"hunger": -2}))
        self.assertNotIn("bread", second)

    def test_a_spec_makes_its_definition(self):
        spec = parse_document(document(item(description="d")))[0][0]
        self.assertEqual(ItemDef("bread", "Bread", "food", {"hunger": -2}, "d"), spec.definition())

    def test_the_effects_of_a_definition_are_a_copy(self):
        spec = parse_document(document())[0][0]
        definition = spec.definition()
        definition.effects["hunger"] = -99
        self.assertEqual({"hunger": -2}, spec.effects)


if __name__ == "__main__":
    unittest.main()
