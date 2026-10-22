
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from itemfeed import ItemFeed, apply_specs, find_shop, MAX_FILE_BYTES
from items import ItemDef, parse_document
from persistence import load_state, save_state

from townhelper import make_sim


BREAD = {"id": "bread", "name": "Bread", "category": "food", "price": 3, "stock": 200, "effects": {"hunger": -2}}


def document(*items):
    return {"format": 1, "items": list(items) or [dict(BREAD)]}


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FeedTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "items"
        self.sim = make_sim()
        self.shop = self.sim.town_hall.shop_buildings[0]
        self.clock = FakeClock()
        self.lines = []
        self.feed = ItemFeed(self.dir, log=self.lines.append, clock=self.clock, stable_seconds=1.0, min_interval=0.0)
        self.feed.ensure_folder()

    def put(self, name, content):
        path = self.dir / name
        if isinstance(content, (dict, list)):
            content = json.dumps(content)
        if isinstance(content, str):
            content = content.encode("utf-8")
        path.write_bytes(content)
        return path

    def ready(self):
        """a file that was just put there is seen, then left alone long enough, then taken over"""
        self.feed.poll(self.sim)
        self.clock.advance(1.5)
        return self.feed.poll(self.sim)

    def log(self):
        return "\n".join(self.lines)

    def names(self):
        return sorted(path.name for path in self.dir.iterdir())


class TestWhichFiles(FeedTestCase):

    def test_only_real_json_files_count(self):
        self.put("bread.json", document())
        self.put("BIG.JSON", document())
        self.put("_old.json", document())
        self.put(".hidden.json", document())
        self.put("notes.txt", "hello")
        self.put("bread.json.bak", "x")
        (self.dir / "folder.json").mkdir()

        self.assertEqual(["BIG.JSON", "bread.json"], [p.name for p in self.feed.candidates()])

    def test_a_missing_folder_is_no_problem(self):
        feed = ItemFeed(self.dir / "nowhere", log=self.lines.append)
        self.assertEqual([], feed.candidates())
        self.assertEqual(0, feed.poll(self.sim))

    def test_the_folder_is_created(self):
        feed = ItemFeed(self.dir / "a" / "b", log=self.lines.append)
        feed.ensure_folder()
        self.assertTrue((self.dir / "a" / "b").is_dir())
        feed.ensure_folder()        # and again is fine


class TestWaiting(FeedTestCase):

    def test_a_new_file_is_first_only_seen(self):
        self.put("bread.json", document())
        self.assertEqual(0, self.feed.poll(self.sim))
        self.assertNotIn("bread", self.shop.stock)

    def test_it_must_stay_unchanged_for_a_second(self):
        self.put("bread.json", document())
        self.feed.poll(self.sim)

        self.clock.advance(0.5)
        self.assertEqual(0, self.feed.poll(self.sim))
        self.clock.advance(0.6)
        self.assertEqual(1, self.feed.poll(self.sim))

    def test_a_file_that_is_still_written_is_not_read(self):
        path = self.put("bread.json", '{"format": 1, "items": [')       # half copied
        self.feed.poll(self.sim)
        self.clock.advance(0.9)
        path.write_text(json.dumps(document()) + " ")                    # it grew: the waiting starts again
        self.assertEqual(0, self.feed.poll(self.sim))
        self.clock.advance(0.9)
        self.assertEqual(0, self.feed.poll(self.sim))
        self.assertEqual([], self.lines)                                 # no complaint about the half file

        self.clock.advance(0.2)
        self.assertEqual(1, self.feed.poll(self.sim))

    def test_the_folder_is_looked_at_only_now_and_then(self):
        feed = ItemFeed(self.dir, log=self.lines.append, clock=self.clock, min_interval=0.25)
        with mock.patch.object(feed, "candidates", return_value=[]) as candidates:
            feed.poll(self.sim)
            feed.poll(self.sim)
            self.assertEqual(1, candidates.call_count)
            self.clock.advance(0.3)
            feed.poll(self.sim)
            self.assertEqual(2, candidates.call_count)


class TestTakingOver(FeedTestCase):

    def test_a_valid_file_is_applied(self):
        self.put("bread.json", document())
        self.assertEqual(1, self.ready())

        offer = self.shop.stock["bread"]
        self.assertEqual((3, 200), (offer.price, offer.quantity))
        self.assertEqual(ItemDef("bread", "Bread", "food", {"hunger": -2}), self.sim.town_hall.catalog.get("bread"))
        self.assertIn("items: bread.json taken over:", self.log())
        self.assertIn("  Bread: +200 at Shop (price 3)", self.log())

    def test_the_file_is_renamed_after_the_finish(self):
        self.put("bread.json", document())
        self.ready()
        self.assertEqual(["bread.json"], self.names())              # not yet

        renamed = self.feed.finish()

        self.assertEqual(["_consumed_bread_1001.json"], renamed)
        self.assertEqual(["_consumed_bread_1001.json"], self.names())
        self.assertIn("items: bread.json -> _consumed_bread_1001.json", self.log())
        self.assertEqual([], self.feed.finish())                     # nothing left to do

    def test_the_name_has_the_whole_name_and_the_timestamp_in_seconds(self):
        self.put("my.great bread.json", document())
        self.ready()
        self.clock.now = 1792506600.9
        self.assertEqual(["_consumed_my.great bread_1792506600.json"], self.feed.finish())

    def test_the_same_name_in_the_same_second_gets_a_number(self):
        self.put("bread.json", document())
        self.put("_consumed_bread_1001.json", "an older file")
        self.put("_consumed_bread_1001_2.json", "and another one")
        self.ready()

        self.assertEqual(["_consumed_bread_1001_3.json"], self.feed.finish())
        self.assertEqual("an older file", (self.dir / "_consumed_bread_1001.json").read_text())

    def test_a_consumed_file_is_never_applied_again(self):
        self.put("bread.json", document())
        self.ready()
        self.feed.finish()
        for _ in range(3):
            self.clock.advance(2)
            self.assertEqual(0, self.feed.poll(self.sim))
        self.assertEqual(200, self.shop.stock["bread"].quantity)

    def test_the_same_content_again_in_a_new_file_adds_again(self):
        self.put("bread.json", document())
        self.ready()
        self.feed.finish()
        self.put("bread.json", document())
        self.ready()
        self.assertEqual(400, self.shop.stock["bread"].quantity)

    def test_several_files_in_name_order(self):
        self.put("b.json", document(dict(BREAD, id="b", name="B")))
        self.put("a.json", document(dict(BREAD, id="a", name="A")))
        self.assertEqual(2, self.ready())
        self.assertLess(self.log().index("A: +200"), self.log().index("B: +200"))
        self.assertEqual(2, len(self.feed.finish()))

    def test_files_with_a_byte_order_mark_work(self):
        # Windows editors add one
        self.put("bread.json", b"\xef\xbb\xbf" + json.dumps(document()).encode("utf-8"))
        self.assertEqual(1, self.ready())

    def test_umlauts_in_names(self):
        self.put("brot.json", document(dict(BREAD, name="Brötchen", description="frisch gebacken ä ö ü")))
        self.assertEqual(1, self.ready())
        self.assertEqual("Brötchen", self.sim.town_hall.catalog.get("bread").name)

    def test_the_game_state_is_changed_while_holding_the_lock(self):
        owned = []
        original = self.shop.restock

        def spy(*args, **kwargs):
            owned.append(self.sim.lock._is_owned())
            return original(*args, **kwargs)

        self.shop.restock = spy
        self.put("bread.json", document())
        self.ready()
        self.assertEqual([True], owned)
        self.assertFalse(self.sim.lock._is_owned())


class TestInvalidFiles(FeedTestCase):

    def test_an_invalid_file_stays_and_every_problem_is_printed(self):
        self.put("bad.json", document(dict(BREAD, price="3", pirce=1)))
        self.assertEqual(0, self.ready())

        self.assertEqual(["bad.json"], self.names())
        self.assertEqual([], self.feed.finish())
        self.assertIn("items: bad.json is not valid, nothing was taken over", self.log())
        self.assertIn('  items[0].price: must be a whole number >= 0, got "3"', self.log())
        self.assertIn('  items[0].pirce: unknown field (did you mean "price"?)', self.log())
        self.assertNotIn("bread", self.shop.stock)

    def test_it_is_reported_only_once(self):
        self.put("bad.json", "{ nope")
        self.ready()
        count = len(self.lines)
        for _ in range(4):
            self.clock.advance(2)
            self.feed.poll(self.sim)
        self.assertEqual(count, len(self.lines))

    def test_it_is_looked_at_again_when_it_changes(self):
        path = self.put("bread.json", "{ nope")
        self.ready()
        self.assertEqual(["bread.json"], self.names())

        path.write_text(json.dumps(document()))
        self.assertEqual(0, self.feed.poll(self.sim))            # changed: waits again
        self.clock.advance(1.5)
        self.assertEqual(1, self.feed.poll(self.sim))
        self.assertEqual(200, self.shop.stock["bread"].quantity)

    def test_all_or_nothing_for_the_checking_of_the_file(self):
        self.put("two.json", document(BREAD, dict(BREAD, id="cake", name="Cake", price="x")))
        self.ready()

        self.assertNotIn("bread", self.shop.stock)
        self.assertNotIn("cake", self.shop.stock)
        self.assertNotIn("bread", self.sim.town_hall.catalog)

    def test_all_or_nothing_for_the_checking_against_the_town(self):
        self.put("two.json", document(BREAD, dict(BREAD, id="cake", name="Cake", store="Nowhere")))
        self.ready()

        self.assertNotIn("bread", self.shop.stock)
        self.assertNotIn("bread", self.sim.town_hall.catalog)
        self.assertIn('items[1].store: no shop named "Nowhere" (shops: Shop)', self.log())

    def test_not_text(self):
        self.put("bin.json", b"\xff\xfe\x00\x01 not utf8 \x80")
        self.ready()
        self.assertIn("(file): is not UTF-8 text", self.log())

    def test_too_large(self):
        self.put("huge.json", b" " * (MAX_FILE_BYTES + 1))
        self.ready()
        self.assertIn(f"(file): too large ({MAX_FILE_BYTES + 1} bytes, at most {MAX_FILE_BYTES})", self.log())

    def test_empty_file(self):
        self.put("empty.json", "")
        self.ready()
        self.assertIn("(file): not valid JSON", self.log())

    def test_unreadable_file(self):
        path = self.put("bread.json", document())
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("locked")):
            self.ready()
        self.assertIn("(file): cannot be read: locked", self.log())
        self.assertTrue(path.exists())

    def test_a_deleted_file_is_forgotten(self):
        path = self.put("bad.json", "{ nope")
        self.ready()
        path.unlink()
        self.feed.poll(self.sim)
        self.assertEqual({}, self.feed.seen)
        self.assertEqual({}, self.feed.finished)


class TestRenameProblems(FeedTestCase):

    def test_a_file_that_cannot_be_renamed_is_not_applied_twice(self):
        self.put("bread.json", document())
        self.ready()

        with mock.patch.object(Path, "rename", side_effect=OSError("locked")):
            self.assertEqual([], self.feed.finish())

        self.assertIn("items: bread.json was applied but cannot be renamed (locked)", self.log())
        for _ in range(3):
            self.clock.advance(2)
            self.assertEqual(0, self.feed.poll(self.sim))
        self.assertEqual(200, self.shop.stock["bread"].quantity)


class TestWhatTheItemsDo(FeedTestCase):

    def apply(self, *items):
        specs, errors = parse_document(json.dumps(document(*items)))
        self.assertEqual([], errors)
        return apply_specs(self.sim, specs)

    def test_a_new_item_in_the_first_shop(self):
        messages, errors = self.apply(BREAD)

        self.assertEqual([], errors)
        self.assertEqual(["Bread: +200 at Shop (price 3)"], messages)
        self.assertEqual((3, 200), (self.shop.stock["bread"].price, self.shop.stock["bread"].quantity))

    def test_restocking_replaces_the_price_and_adds_the_pieces(self):
        self.apply(BREAD)
        messages, errors = self.apply(dict(BREAD, price=4, stock=50))

        self.assertEqual([], errors)
        self.assertEqual((4, 250), (self.shop.stock["bread"].price, self.shop.stock["bread"].quantity))

    def test_a_new_price_without_new_pieces(self):
        self.apply(BREAD)
        messages, _ = self.apply(dict(BREAD, price=9, stock=0))

        self.assertEqual(["Bread: price at Shop is now 9"], messages)
        self.assertEqual((9, 200), (self.shop.stock["bread"].price, self.shop.stock["bread"].quantity))

    def test_the_plain_food_can_get_a_new_price(self):
        plain = {"id": "food", "name": "food", "category": "food", "price": 8, "stock": 0, "effects": {"hunger": -1}}
        _, errors = self.apply(plain)

        self.assertEqual([], errors)
        self.assertEqual((8, math.inf), (self.shop.stock["food"].price, self.shop.stock["food"].quantity))

    def test_name_and_description_may_change_but_not_category_and_effects(self):
        self.apply(BREAD)
        _, errors = self.apply(dict(BREAD, name="Fine Bread", description="better"))
        self.assertEqual([], errors)
        self.assertEqual("Fine Bread", self.sim.town_hall.catalog.get("bread").name)

        _, errors = self.apply(dict(BREAD, effects={"hunger": -5}))
        self.assertEqual(1, len(errors))
        self.assertIn('items[0]: "bread" already exists as a food with the effects {\'hunger\': -2}', errors[0])
        self.assertEqual({"hunger": -2}, self.sim.town_hall.catalog.get("bread").effects)
        self.assertEqual(400, self.shop.stock["bread"].quantity)        # the rejected file added nothing

    def test_the_same_id_with_other_effects_in_another_shop_is_the_same_conflict(self):
        other = type(self.shop)("Second", work_places=1)
        self.sim.town_hall.add_building(other)
        self.apply(BREAD)
        _, errors = self.apply(dict(BREAD, store="Second", effects={"hunger": -3}))
        self.assertEqual(1, len(errors))
        self.assertNotIn("bread", other.stock)

    def test_the_same_id_twice_in_one_file_with_different_effects(self):
        second = type(self.shop)("Second", work_places=1)
        self.sim.town_hall.add_building(second)

        _, errors = self.apply(dict(BREAD, store="Shop"), dict(BREAD, store="Second", effects={"hunger": -9}))

        self.assertEqual(1, len(errors))
        self.assertTrue(errors[0].startswith('items[1]: "bread" already exists as a food'), errors[0])
        self.assertNotIn("bread", self.shop.stock)              # all or nothing, also for the first one
        self.assertNotIn("bread", second.stock)

    def test_the_plain_food_with_other_effects_is_a_conflict(self):
        plain = {"id": "food", "name": "food", "category": "food", "price": 8, "stock": 0, "effects": {"hunger": -4}}
        _, errors = self.apply(plain)
        self.assertEqual(1, len(errors))
        self.assertEqual(5, self.shop.stock["food"].price)

    def test_a_named_shop(self):
        other = type(self.shop)("Second Shop", work_places=1)
        self.sim.town_hall.add_building(other)

        _, errors = self.apply(dict(BREAD, store="second SHOP"))

        self.assertEqual([], errors)
        self.assertIn("bread", other.stock)
        self.assertNotIn("bread", self.shop.stock)

    def test_an_unknown_shop(self):
        _, errors = self.apply(dict(BREAD, store="Nowhere"))
        self.assertEqual(['items[0].store: no shop named "Nowhere" (shops: Shop)'], errors)

    def test_two_shops_with_the_same_name(self):
        self.sim.town_hall.add_building(type(self.shop)("Shop", work_places=1))
        _, errors = self.apply(dict(BREAD, store="Shop"))
        self.assertEqual(['items[0].store: 2 shops are named "Shop", rename one of them'], errors)

    def test_no_shop_at_all(self):
        sim = make_sim()
        sim.town_hall.shop_buildings.clear()
        specs, _ = parse_document(json.dumps(document(BREAD)))
        _, errors = apply_specs(sim, specs)
        self.assertEqual(["items[0]: the town has no shop"], errors)

    def test_find_shop(self):
        shop, problem = find_shop(self.sim.town_hall, None)
        self.assertIs(self.shop, shop)
        self.assertIsNone(problem)

    def test_a_gift(self):
        maxima = next(p for p in self.sim.town_hall.citizens if p.name == "Maxima")
        gift = dict(BREAD, id="golden_apple", name="Golden Apple", price=0, stock=2,
                    effects={"hunger": -5}, deliver_to="Maxima")

        messages, errors = self.apply(gift)

        self.assertEqual([], errors)
        self.assertEqual(["Golden Apple: 2 given to Maxima"], messages)
        self.assertEqual(2, maxima.inventory["golden_apple"])
        self.assertIn("received 2 Golden Apple as a gift", maxima.log[-1][2])
        self.assertEqual({"hunger": -5}, self.sim.town_hall.catalog.get("golden_apple").effects)
        self.assertNotIn("golden_apple", self.shop.stock)             # it did not go to the shop

    def test_a_gift_is_added_to_what_is_already_there(self):
        maxima = next(p for p in self.sim.town_hall.citizens if p.name == "Maxima")
        gift = dict(BREAD, id="gem", name="Gem", price=0, stock=1, deliver_to="max")
        self.apply(gift)
        self.apply(gift)
        self.assertEqual(2, maxima.inventory["gem"])

    def test_a_gift_for_somebody_who_does_not_exist(self):
        _, errors = self.apply(dict(BREAD, stock=1, deliver_to="Nobody"))
        self.assertEqual(["items[0].deliver_to: no npc named 'Nobody'"], errors)

    def test_a_gift_for_somebody_who_is_dead(self):
        self.sim.run(10)                    # Dave starves in cycle 10
        _, errors = self.apply(dict(BREAD, stock=1, deliver_to="Dave"))
        self.assertEqual(["items[0].deliver_to: Dave died in cycle 10 (starvation)"], errors)

    def test_a_gift_for_a_name_that_fits_several(self):
        _, errors = self.apply(dict(BREAD, stock=1, deliver_to="Al"))
        self.assertEqual(1, len(errors))
        self.assertIn("2 npcs match 'Al'", errors[0])

    def test_a_gift_needs_at_least_one_piece(self):
        _, errors = self.apply(dict(BREAD, stock=0, deliver_to="Maxima"))
        self.assertEqual(["items[0].stock: must be at least 1 when the item is given to a sim"], errors)

    def test_a_gift_and_a_shop_item_in_one_file(self):
        maxima = next(p for p in self.sim.town_hall.citizens if p.name == "Maxima")
        _, errors = self.apply(BREAD, dict(BREAD, id="gem", name="Gem", stock=1, deliver_to="Maxima"))
        self.assertEqual([], errors)
        self.assertIn("bread", self.shop.stock)
        self.assertEqual(1, maxima.inventory["gem"])

    def test_a_gift_file_goes_through_the_feed(self):
        self.put("gift.json", document(dict(BREAD, id="gem", name="Gem", price=0, stock=1, deliver_to="Maxima")))
        self.assertEqual(1, self.ready())
        self.assertIn("  Gem: 1 given to Maxima", self.log())


class TestInTheGameLoop(FeedTestCase):

    def run_cycles(self, cycles, feed, save_path):
        with contextlib.redirect_stdout(io.StringIO()):
            return main.run_cycles(self.sim, cycles, save_path, feed=feed)

    def test_apply_then_save_then_rename(self):
        events = []

        class Recorder:
            def poll(self, sim):
                events.append("poll")

            def finish(self):
                events.append("finish")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("main.save_state", side_effect=lambda sim, path: events.append("save")):
            self.run_cycles(2, Recorder(), Path(tmp) / "save.pkl")

        self.assertEqual(["poll", "save", "finish"] * 2, events)

    def test_items_are_in_the_save_before_the_file_is_renamed(self):
        self.put("bread.json", document())
        feed = ItemFeed(self.dir, log=self.lines.append, stable_seconds=0, min_interval=0)
        seen = []

        def spy(sim, path):
            seen.append(("bread" in self.shop.stock, (self.dir / "bread.json").exists()))
            save_state(sim, path)

        with tempfile.TemporaryDirectory() as tmp, mock.patch("main.save_state", side_effect=spy):
            self.run_cycles(3, feed, Path(tmp) / "save.pkl")

        # cycle 1: the file is only seen, cycle 2: applied but not yet renamed while saving, cycle 3: renamed
        self.assertEqual([(False, True), (True, True), (True, False)], seen)

    def test_the_saved_game_has_the_items(self):
        self.put("bread.json", document())
        feed = ItemFeed(self.dir, log=self.lines.append, stable_seconds=0, min_interval=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "save.pkl"
            self.run_cycles(3, feed, path)
            loaded = load_state(path)

        offer = loaded.town_hall.shop_buildings[0].stock["bread"]
        self.assertTrue(0 < offer.quantity <= 200, offer)       # the sims have started to buy it
        self.assertEqual(3, offer.price)
        self.assertIn("bread", loaded.town_hall.catalog)

    def test_without_a_feed_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(2, self.run_cycles(2, None, Path(tmp) / "save.pkl"))


class TestOptionsOfMain(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.save = str(self.tmp / "save.pkl")

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main.main(["--save-file", self.save, "--no-server", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_default_folder_is_next_to_main_py(self):
        self.assertEqual(Path(main.__file__).resolve().parent / "items", main.ITEMS_DIR)
        self.assertEqual(main.ITEMS_DIR, main.parse_args([]).items_dir)

    def test_the_folder_is_made_and_announced(self):
        folder = self.tmp / "my items"
        code, out, _ = self.run_main("--new", "-c", "1", "--items-dir", str(folder))

        self.assertEqual(0, code)
        self.assertTrue(folder.is_dir())
        self.assertIn(f"items: put JSON files into {folder}", out)

    def test_a_file_in_the_folder_is_taken_over_while_the_game_runs(self):
        folder = self.tmp / "items"
        folder.mkdir()
        (folder / "bread.json").write_text(json.dumps(document()))

        original = ItemFeed.__init__

        def quick(self, directory, **kwargs):
            original(self, directory, stable_seconds=0.0, min_interval=0.0)

        with mock.patch.object(ItemFeed, "__init__", quick):
            code, out, _ = self.run_main("--new", "-c", "3", "--items-dir", str(folder))

        self.assertEqual(0, code)
        self.assertIn("items: bread.json taken over:", out)
        self.assertEqual([], [p.name for p in folder.iterdir() if not p.name.startswith("_consumed_bread_")])
        loaded = load_state(self.save)
        self.assertIn("bread", loaded.town_hall.shop_buildings[0].stock)
        self.assertIn("bread", loaded.town_hall.catalog)

    def test_no_items(self):
        folder = self.tmp / "items"
        code, out, _ = self.run_main("--new", "-c", "1", "--items-dir", str(folder), "--no-items")

        self.assertEqual(0, code)
        self.assertFalse(folder.exists())
        self.assertNotIn("items:", out)

    def test_a_folder_that_cannot_be_made_is_only_a_warning(self):
        blocker = self.tmp / "items"
        blocker.write_text("I am a file")
        code, out, err = self.run_main("--new", "-c", "2", "--items-dir", str(blocker))

        self.assertEqual(0, code)
        self.assertIn("warning: cannot use the items folder", err)
        self.assertEqual(2, load_state(self.save).cycle)

    def test_empty_shops(self):
        self.run_main("--new", "-c", "0", "--no-items", "--empty-shops")
        shop = load_state(self.save).town_hall.shop_buildings[0]
        self.assertEqual({}, shop.stock)

    def test_the_default_is_a_shop_with_food(self):
        self.run_main("--new", "-c", "0", "--no-items")
        shop = load_state(self.save).town_hall.shop_buildings[0]
        self.assertEqual(["food"], list(shop.stock))
        self.assertEqual(math.inf, shop.stock["food"].quantity)

    def test_empty_shops_do_not_apply_to_a_town_that_is_resumed(self):
        self.run_main("--new", "-c", "1", "--no-items")
        code, _, err = self.run_main("-c", "0", "--no-items", "--empty-shops")

        self.assertEqual(0, code)
        self.assertIn("--empty-shops only counts for a new town", err)
        self.assertEqual(["food"], list(load_state(self.save).town_hall.shop_buildings[0].stock))


if __name__ == "__main__":
    unittest.main()
