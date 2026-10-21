
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from buildings import MegaBuilding, WorkBuilding
from persistence import SaveError, load_state, save_state, SAVE_VERSION
from person import Person
from services import TownHall
from simulation import Simulation


def make_sim(people=3):
    """small town: everybody has a home and a job, everybody starves after 10 days"""
    town = TownHall("Testville")
    home = MegaBuilding("Home", stories=people, persons_per_unit=1, money=0)
    job = WorkBuilding("Job", work_places=people)
    town.add_building(home)
    town.add_building(job)

    for nr in range(people):
        person = Person(name=f"P{nr}", routine=1 + nr % 5)
        town.add_citizen(person)
        person.find_place_to_live(town.list_of_buildings())
        job.employ(person)

    return Simulation(town)


def run_quiet(*args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = main.main(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


class PersistenceTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "save.pkl"


class TestSaveLoad(PersistenceTestCase):

    def test_roundtrip_continues_identically(self):
        sim = make_sim()
        sim.run(3)
        save_state(sim, self.path)

        loaded = load_state(self.path)
        self.assertEqual(sim.cycle, loaded.cycle)
        self.assertEqual(sim.deaths, loaded.deaths)

        sim.run(4)
        loaded.run(4)

        self.assertEqual(sim.cycle, loaded.cycle)
        self.assertEqual(sim.deaths, loaded.deaths)
        self.assertEqual(
            [(p.name, p.attributes.hunger, p.alive) for p in sim.town_hall.citizens],
            [(p.name, p.attributes.hunger, p.alive) for p in loaded.town_hall.citizens],
        )

    def test_object_links_survive(self):
        sim = make_sim()
        sim.step()
        sim.step()
        save_state(sim, self.path)
        loaded = load_state(self.path)

        town = loaded.town_hall
        job = town.work_buildings[0]
        for person in town.citizens:
            self.assertIn(person, person.home.owners)
            self.assertIs(person.home, person.home.building.units[person.home.unit_number])
            self.assertIn(person.home.building, town.home_buildings)
            self.assertIn(person, job.employees)
            self.assertIs(person.workplace, job)
            # whoever is somewhere is also registered there
            self.assertIn(person, person.current_location.currently_here)

    def test_no_temp_files_left(self):
        save_state(make_sim(), self.path)
        self.assertEqual([self.path.name], [p.name for p in self.path.parent.iterdir()])

    def test_failed_save_keeps_old_save(self):
        sim = make_sim()
        save_state(sim, self.path)
        before = self.path.read_bytes()

        with mock.patch("persistence.pickle.dump", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                save_state(sim, self.path)

        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([self.path.name], [p.name for p in self.path.parent.iterdir()])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            load_state(self.path)

    def test_garbage_file(self):
        self.path.write_text("garbage")
        with self.assertRaises(SaveError):
            load_state(self.path)

    def test_wrong_version(self):
        import pickle
        self.path.write_bytes(pickle.dumps({"version": SAVE_VERSION + 1}))
        with self.assertRaises(SaveError):
            load_state(self.path)


class TestRunCycles(PersistenceTestCase):

    def test_saves_after_every_cycle(self):
        sim = make_sim()
        with mock.patch("main.save_state", wraps=save_state) as saver, contextlib.redirect_stdout(io.StringIO()):
            days = main.run_cycles(sim, 3, self.path)

        self.assertEqual(3, days)
        self.assertEqual(3, saver.call_count)
        self.assertEqual(3, load_state(self.path).cycle)

    def test_zero_cycles(self):
        sim = make_sim()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main.run_cycles(sim, 0, self.path))
        self.assertEqual(0, sim.cycle)

    def test_unlimited_stops_when_everybody_is_dead(self):
        sim = make_sim()
        with contextlib.redirect_stdout(io.StringIO()):
            days = main.run_cycles(sim, None, self.path)

        self.assertEqual(10, days)
        self.assertEqual(3, sim.deaths)


class TestCommandLine(PersistenceTestCase):

    def args(self, *extra):
        return [*extra, "--save-file", str(self.path), "--no-server"]

    def test_new_then_resume(self):
        code, out, _ = run_quiet(self.args("-c", "2", "--new"))
        self.assertEqual(0, code)
        self.assertIn("started a new town", out)
        self.assertEqual(2, load_state(self.path).cycle)

        code, out, _ = run_quiet(self.args("--cycles=3"))
        self.assertEqual(0, code)
        self.assertIn("resumed", out)
        self.assertEqual(5, load_state(self.path).cycle)

    def test_new_overwrites_existing_save(self):
        run_quiet(self.args("-c", "2", "--new"))
        run_quiet(self.args("-c", "1", "--new"))
        self.assertEqual(1, load_state(self.path).cycle)

    def test_corrupt_save_is_not_overwritten(self):
        self.path.write_text("garbage")

        code, _, err = run_quiet(self.args("-c", "1"))

        self.assertEqual(1, code)
        self.assertIn("--new", err)
        self.assertEqual("garbage", self.path.read_text())

        code, _, _ = run_quiet(self.args("-c", "1", "--new"))
        self.assertEqual(0, code)

    def test_negative_cycles_rejected(self):
        with self.assertRaises(SystemExit):
            run_quiet(self.args("-c", "-1"))

    def test_ctrl_c_goes_back_to_last_save(self):
        run_quiet(self.args("-c", "2", "--new"))

        with mock.patch("main.run_cycles", side_effect=KeyboardInterrupt):
            code, out, _ = run_quiet(self.args())

        self.assertEqual(0, code)
        self.assertIn("last saved state: cycle 2", out)

    def test_each_new_town_has_its_own_maxima(self):
        # no state may leak from one new town into the next
        run_quiet(self.args("-c", "1", "--new"))
        first = load_state(self.path).town_hall
        run_quiet(self.args("-c", "1", "--new"))
        second = load_state(self.path).town_hall

        self.assertIsNot(first.citizens[-1], second.citizens[-1])
        self.assertEqual("Maxima", second.citizens[-1].name)


if __name__ == "__main__":
    unittest.main()
