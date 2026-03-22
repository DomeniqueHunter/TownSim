
import unittest

from sim import Sim
from stats import Stats


class TestSim(unittest.TestCase):

    def test_sim_aging(self):
        sim = Sim(name="TestSim")
        round_malus = Stats(hunger=1)

        for _ in range(10):
            if not sim.alive: continue

            sim.attributes += round_malus
            sim.check()

        self.assertEqual(sim.alive, False)

    def test_interactions(self):
        sim1 = Sim(name="Sim1")

        sim1.home = "Home1"
        sim1.workplace = "Workplace1"

        # meeting at else location
        sim1.current_location = "Else"
        print(sim1.interactions())


if __name__ == "__main__":
    unittest.main()
