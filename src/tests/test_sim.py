
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


if __name__ == "__main__":
    unittest.main()
