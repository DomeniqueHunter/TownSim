
import contextlib
import io
import re
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
import protocol
from persistence import load_state

from townhelper import make_sim


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class MainOptionsTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.save = str(Path(tmp.name) / "save.pkl")

    def args(self, *extra):
        return ["--new", "--save-file", self.save, *extra]


class TestParsing(unittest.TestCase):

    def test_defaults(self):
        args = main.parse_args([])
        self.assertEqual(0.0, args.delay)
        self.assertEqual(protocol.DEFAULT_PORT, args.port)
        self.assertFalse(args.no_server)
        self.assertIsNone(args.cycles)

    def test_options(self):
        args = main.parse_args(["-d", "0.5", "--port", "9000", "--no-server", "-c", "4"])
        self.assertEqual((0.5, 9000, True, 4), (args.delay, args.port, args.no_server, args.cycles))

    def test_bad_delay(self):
        for bad in ("-1", "slow"):
            with self.subTest(delay=bad), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main.parse_args(["--delay", bad])


class TestServerOption(MainOptionsTestCase):

    def test_server_is_announced_and_stopped_again(self):
        code, out, _ = run_main(*self.args("-c", "1", "--port", "0"))

        self.assertEqual(0, code)
        match = re.search(r"console.py and display.py can connect on 127\.0\.0\.1:(\d+)", out)
        self.assertTrue(match, out)
        # the game is over, nobody listens anymore
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", int(match.group(1))), timeout=1)

    def test_no_server(self):
        with mock.patch("main.GameServer") as server:
            code, out, _ = run_main(*self.args("-c", "1", "--no-server"))
        self.assertEqual(0, code)
        server.assert_not_called()
        self.assertNotIn("can connect", out)

    def test_port_in_use_is_only_a_warning(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            code, out, err = run_main(*self.args("-c", "2", "--port", str(taken.getsockname()[1])))

        self.assertEqual(0, code)
        self.assertIn("warning: no console server", err)
        self.assertIn("--port", err)
        self.assertEqual(2, load_state(self.save).cycle)       # the game ran anyway


class TestDelay(MainOptionsTestCase):

    def delay_used(self, *extra):
        with mock.patch("main.run_cycles", return_value=0) as runner:
            run_main(*self.args("-c", "1", "--port", "0", *extra))
        return runner.call_args.args[3]

    def test_a_tiny_pause_while_the_server_is_up(self):
        # lets the server thread look at the town between two phases
        self.assertEqual(main.MIN_PHASE_DELAY, self.delay_used())

    def test_no_pause_without_server(self):
        self.assertEqual(0.0, self.delay_used("--no-server"))

    def test_chosen_delay_is_used(self):
        self.assertEqual(0.5, self.delay_used("--delay", "0.5"))
        self.assertEqual(0.5, self.delay_used("--delay", "0.5", "--no-server"))

    def test_run_cycles_hands_the_delay_to_every_phase(self):
        sim = make_sim()
        with mock.patch("simulation.time.sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
            main.run_cycles(sim, 2, self.save, phase_delay=0.25)
        self.assertEqual(20, sleep.call_count)
        sleep.assert_called_with(0.25)


if __name__ == "__main__":
    unittest.main()
