
import unittest

from stats import Attributes
from buildings import MegaBuilding, Mansion
from person import Person


class TestBuildings(unittest.TestCase):

    def test_location_stats_do_not_change_building(self):
        mansion = Mansion("Mansion Maxima")
        unit = mansion.get_unit(0)

        first = str(unit.location_stats())
        second = str(unit.location_stats())

        self.assertEqual(first, second)
        # the building's own gain stats must stay untouched
        self.assertEqual(mansion.gain_stats.money, 0)

    def test_max_residents(self):
        mb = MegaBuilding("Block", stories=3, units_per_story=2, persons_per_unit=4)
        self.assertEqual(24, mb.max_residents)

    def test_rent(self):
        self.assertEqual(1000, Mansion("M").rent())
        self.assertEqual(0, MegaBuilding("Free", money=0).rent())

    def test_full_building_does_not_crash(self):
        mb = MegaBuilding("Tiny", stories=1, persons_per_unit=1, money=0)
        a, b = Person(name="a"), Person(name="b")

        self.assertTrue(a.find_place_to_live([mb]))
        self.assertFalse(b.find_place_to_live([mb]))
        self.assertIsNone(b.home)

    def test_cannot_afford_rent(self):
        mansion = Mansion("Rich only")
        poor = Person(name="poor")

        self.assertFalse(poor.find_place_to_live([mansion]))


if __name__ == "__main__":
    unittest.main()
