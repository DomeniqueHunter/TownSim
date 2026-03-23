
import unittest

from person import Person
from stats_new import Stats, Attributes
import math


class TestStats(unittest.TestCase):

    def test_stats_attr(self):
        stats1 = Stats(health=10, money=-2)
        stats2 = Stats(health=1, money=5)
        stats3 = stats1 + stats2
        self.assertEqual(11, stats3.health)

    def test_stats_dict(self):
        attr = {"stamina": 5, "meow": 1}
        stats1 = Stats(attr)
        stats2 = Stats(stamina=1, meow=5)
        stats3 = stats1 + stats2
        self.assertEqual(6, stats3.meow)

    def test_attributes_attr(self):
        attributes = Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=(0, 199999))
        person = Person(name="TestPerson", attributes=attributes)

        self.assertEqual(person.name, "TestPerson")

    def test_attributes_dict(self):
        attr = {"health": (1000, 1000), "stamina": (1000, 1000), "hunger": (0, 10_000), "money": (0, 199999)}
        attributes = Attributes(attr)
        person = Person(name="TestPerson", attributes=attributes)

        self.assertEqual(person.name, "TestPerson")

    def test_add_attributes_stats(self):
        attributes = Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(10, 10_000), money=(10, math.inf))
        stats = Stats(health=-10, money=-2)

        attributes += stats
        self.assertEqual(990, attributes.health)
        self.assertEqual(8, attributes.money)
        self.assertEqual(1000, attributes.stamina)
        self.assertEqual(10, attributes.hunger)


if __name__ == "__main__":
    unittest.main()
