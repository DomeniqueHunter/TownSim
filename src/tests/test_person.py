
import unittest

from person import Person
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

    def test_interactions(self):
        person1 = Person(name="Person1")

        person1.home = "Home1"
        person1.workplace = "Workplace1"

        # meeting at else location
        person1.current_location = "Else"
        print(person1.interactions())


if __name__ == "__main__":
    unittest.main()
