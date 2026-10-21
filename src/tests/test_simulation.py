
import unittest

from services import TownHall
from simulation import Simulation, PHASES
from person import Person, DayTime
from buildings import MegaBuilding, WorkBuilding


def make_town(workplace=False):
    """one person (routine 1) in its own home, optionally with a job"""
    town = TownHall("Testville")
    home = MegaBuilding("Home", stories=1, persons_per_unit=1, money=0)
    town.add_building(home)

    person = Person(name="Tester", routine=1)
    town.add_citizen(person)
    person.find_place_to_live(town.list_of_buildings())

    job = None
    if workplace:
        job = WorkBuilding("Job")
        town.add_building(job)
        job.employ(person)

    return town, person, job


class TestSimulation(unittest.TestCase):

    def test_day_has_all_phases(self):
        town, _, _ = make_town()
        sim = Simulation(town)

        phases = [sim.step() for _ in range(len(PHASES))]

        self.assertEqual(list(DayTime), phases)
        self.assertEqual(1, sim.cycle)
        self.assertEqual(DayTime.MORNING, sim.phase)

    def test_run_cycle(self):
        town, _, _ = make_town()
        sim = Simulation(town)

        sim.step()
        sim.run_cycle()    # finishes the day that is already running

        self.assertEqual(1, sim.cycle)
        self.assertEqual(DayTime.MORNING, sim.phase)

    def test_follows_routine(self):
        town, person, job = make_town(workplace=True)
        sim = Simulation(town)

        sim.step()  # MORNING: wake up
        self.assertEqual(person.home, person.current_location)

        sim.step()  # MORNING_MOVEMENT: go to work
        self.assertIs(job, person.current_location)

        sim.step()  # NOON: work
        self.assertIs(job, person.current_location)

        sim.step()  # NOON_MOVEMENT: go to shop, there is none -> home
        self.assertEqual(person.home, person.current_location)

    def test_no_workplace_means_staying_home(self):
        town, person, _ = make_town()
        sim = Simulation(town)

        for _ in range(len(PHASES)):
            sim.step()
            self.assertEqual(person.home, person.current_location)

    def test_census(self):
        town, _, _ = make_town(workplace=True)
        sim = Simulation(town)

        sim.step()
        self.assertEqual({"home": 1}, dict(sim.census()))

        sim.step()
        self.assertEqual({"Job": 1}, dict(sim.census()))

    def test_starvation_after_ten_days(self):
        town, person, job = make_town(workplace=True)
        home = person.home
        sim = Simulation(town)

        days = sim.run(9)
        self.assertEqual(9, days)
        self.assertTrue(person.alive)

        sim.run(1)
        self.assertFalse(person.alive)
        self.assertEqual(1, sim.deaths)
        self.assertEqual([], town.citizens)
        self.assertEqual(0, home.owners.__len__())
        self.assertEqual([], job.employees)
        self.assertEqual([], home.currently_here)

    def test_run_stops_when_everybody_is_dead(self):
        town, _, _ = make_town()
        sim = Simulation(town)

        self.assertEqual(10, sim.run(50))
        self.assertEqual(0, sim.run(5))


if __name__ == "__main__":
    unittest.main()
