
import unittest

from person import Person, maxima
from buildings import MegaBuilding
from stats import Stats


class TestPerson(unittest.TestCase):

    def test_person_aging(self):
        person = Person(name="TestPerson")
        round_malus = Stats(hunger=1)

        for _ in range(10):
            if not person.alive: continue

            person.attributes += round_malus
            person.check()

        self.assertEqual(person.alive, False)

    def test_random_routine(self):
        # no routine given -> must not crash and must pick a valid one
        person = Person(name="Random")
        self.assertIsNotNone(person.routine)

    def test_invalid_routine_falls_back_to_random(self):
        person = Person(name="Invalid", routine=99)
        self.assertIsNotNone(person.routine)

    def test_death_frees_home(self):
        mb = MegaBuilding("Home", stories=1, persons_per_unit=1, money=0)
        person = Person(name="Mortal")
        person.find_place_to_live([mb])
        person.go(person.home)

        person.die()

        self.assertFalse(person.alive)
        self.assertIsNone(person.home)
        self.assertIsNone(person.current_location)
        self.assertEqual(0, mb.residents())

    def test_go_leaves_previous_location(self):
        a = MegaBuilding("A", stories=1, persons_per_unit=1, money=0).get_unit(0)
        b = MegaBuilding("B", stories=1, persons_per_unit=1, money=0).get_unit(0)
        person = Person(name="Walker")

        person.go(a)
        person.go(b)

        self.assertNotIn(person, a.currently_here)
        self.assertIn(person, b.currently_here)

    def test_maxima_is_rich(self):
        self.assertEqual(float("inf"), maxima.money())

    @unittest.skip("Person.interactions() is not implemented yet")
    def test_interactions(self):
        person1 = Person(name="Person1")

        person1.home = "Home1"
        person1.workplace = "Workplace1"

        # meeting at else location
        person1.current_location = "Else"
        print(person1.interactions())


if __name__ == "__main__":
    unittest.main()
