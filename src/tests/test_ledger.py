
import pickle
import unittest
from unittest import mock

from buildings import MegaBuilding, WorkBuilding, Shop
from ledger import Ledger
from person import Person, DayTime
from services import TownHall
from simulation import Simulation, PHASES
from stats import Stats

from townhelper import make_sim


class TestLedger(unittest.TestCase):

    def test_record_and_close_day(self):
        ledger = Ledger()
        ledger.record("food_bought", 3)
        ledger.record("food_bought", 2)
        ledger.record("food_eaten")

        entry = ledger.close_day(1, alive=7)

        self.assertEqual({"day": 1, "food_bought": 5, "food_eaten": 1, "money_spent": 0,
                          "wages_paid": 0, "leisure_spent": 0, "alive": 7}, entry)
        self.assertEqual(0, sum(ledger.today.values()))
        self.assertEqual(5, ledger.total["food_bought"])
        self.assertEqual([entry], list(ledger.history))

    def test_zero_amounts_are_ignored(self):
        ledger = Ledger()
        ledger.record("food_bought", 0)
        self.assertEqual({}, dict(ledger.total))

    def test_history_is_limited(self):
        ledger = Ledger()
        for day in range(1, Ledger.HISTORY_DAYS + 50):
            ledger.close_day(day)

        self.assertEqual(Ledger.HISTORY_DAYS, len(ledger.history))
        self.assertEqual(Ledger.HISTORY_DAYS + 49, ledger.history[-1]["day"])


class TestPersonBookkeeping(unittest.TestCase):

    def setUp(self):
        self.town = TownHall("T")
        self.shop = Shop("S", food_price=5)
        self.home = MegaBuilding("H", stories=1, persons_per_unit=1, money=0)
        self.town.add_building(self.shop)
        self.town.add_building(self.home)

        self.person = Person(name="Pete", routine=1)
        self.person.attributes += Stats(money=100, hunger=2)
        self.town.add_citizen(self.person)
        self.person.find_place_to_live(self.town.list_of_buildings())
        self.person.find_shop(self.town.shop_buildings)

    def test_citizen_gets_the_town_ledger(self):
        self.assertIs(self.town.ledger, self.person.ledger)

    def test_buying_is_recorded(self):
        self.person.go(self.shop)
        self.person.buy_food(DayTime.AFTERNOON)

        self.assertEqual(3, self.person.totals["food_bought"])
        self.assertEqual(15, self.person.totals["money_spent"])
        self.assertEqual(3, self.town.ledger.today["food_bought"])
        self.assertEqual(15, self.town.ledger.today["money_spent"])
        self.assertEqual((1, "AFTERNOON", "bought 3 food for 15"), self.person.log[-1])

    def test_eating_is_recorded(self):
        self.person.inventory["food"] = 5
        self.person.go(self.person.home)
        self.person.eat(DayTime.MORNING)

        self.assertEqual(2, self.person.totals["food_eaten"])
        self.assertEqual(2, self.town.ledger.today["food_eaten"])
        self.assertEqual((1, "MORNING", "ate 2 food"), self.person.log[-1])

    def test_earning_is_recorded(self):
        self.person.earn(25, DayTime.NOON, "Job")

        self.assertEqual(125, self.person.money())
        self.assertEqual(25, self.person.totals["money_earned"])
        self.assertEqual(25, self.town.ledger.today["wages_paid"])
        self.assertEqual("earned 25 at Job", self.person.log[-1][2])

    def test_nothing_recorded_when_nothing_happens(self):
        self.person.go(self.shop)
        self.person.inventory["food"] = 3
        self.person.buy_food(DayTime.AFTERNOON)       # stock is full
        self.person.eat(DayTime.MORNING)              # not at home

        self.assertEqual(0, len(self.person.log))
        self.assertEqual({}, dict(self.person.totals))

    def test_shop_counts_what_it_sold(self):
        self.person.go(self.shop)
        self.person.buy_food()
        self.assertEqual(3, self.shop.sold)

    def test_person_without_town_still_works(self):
        loner = Person(name="Loner")
        loner.attributes += Stats(money=50)
        loner.earn(10)
        self.assertEqual(60, loner.money())
        self.assertEqual((0, None, "earned 10"), loner.log[-1])

    def test_log_is_limited(self):
        for _ in range(50):
            self.person.earn(1)
        self.assertEqual(12, len(self.person.log))


class TestSimulationExtras(unittest.TestCase):

    def test_clock(self):
        sim = make_sim()
        self.assertEqual({"cycle": 0, "day": 1, "phase": None, "next_phase": "MORNING"}, sim.clock())

        for _ in range(3):
            sim.step()
        self.assertEqual({"cycle": 0, "day": 1, "phase": PHASES[2].name, "next_phase": PHASES[3].name}, sim.clock())

        for _ in range(7):
            sim.step()
        # the day is over, the last phase of it is still what we see
        self.assertEqual({"cycle": 1, "day": 1, "phase": PHASES[-1].name, "next_phase": "MORNING"}, sim.clock())

        sim.step()
        self.assertEqual(2, sim.clock()["day"])
        self.assertEqual("MORNING", sim.clock()["phase"])

    def test_ledger_day_follows_the_simulation(self):
        sim = make_sim()
        sim.run(2)
        sim.step()
        self.assertEqual(3, sim.town_hall.ledger.day)

    def test_every_day_is_booked_in_the_history(self):
        sim = make_sim()
        sim.run(3)

        history = list(sim.town_hall.ledger.history)
        self.assertEqual([1, 2, 3], [entry["day"] for entry in history])
        self.assertEqual(5, history[-1]["alive"])
        self.assertIn("food_stock", history[-1])
        self.assertGreater(history[0]["food_bought"], 0)

    def test_deaths_are_written_down(self):
        sim = make_sim()
        sim.run(10)         # Dave has no job, no money -> starves on day 10

        self.assertEqual([("Dave", 10, "starvation")], list(sim.town_hall.graveyard))
        self.assertEqual(4, sim.town_hall.ledger.history[-1]["alive"])

    def test_simulation_can_be_pickled_and_still_runs(self):
        sim = make_sim()
        sim.run(2)

        loaded = pickle.loads(pickle.dumps(sim))
        self.assertIsNot(sim.lock, loaded.lock)
        loaded.run(2)

        sim.run(2)
        self.assertEqual(sim.totals(), loaded.totals())

    def test_lock_is_held_while_a_phase_runs(self):
        sim = make_sim()
        owned = []
        original = Person.action

        def spy(person, phase):
            owned.append(sim.lock._is_owned())
            return original(person, phase)

        with mock.patch.object(Person, "action", spy):
            sim.step()

        self.assertTrue(owned)
        self.assertTrue(all(owned))
        self.assertFalse(sim.lock._is_owned())

    def test_phase_delay(self):
        sim = make_sim()
        with mock.patch("simulation.time.sleep") as sleep:
            sim.run_cycle(phase_delay=0.5)
        self.assertEqual(10, sleep.call_count)
        sleep.assert_called_with(0.5)


if __name__ == "__main__":
    unittest.main()
