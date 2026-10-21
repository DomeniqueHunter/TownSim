
import json
import socket
import threading
import unittest

import protocol
from client import GameClient, GameError, GameConnectionError
from gameserver import GameServer

from townhelper import make_sim


class ServerTestCase(unittest.TestCase):

    def setUp(self):
        self.sim = make_sim()
        self.sim.run(2)
        self.server = GameServer(self.sim, port=0)
        self.server.start()
        self.addCleanup(self.stop_server)

        self.client = GameClient(port=self.server.port, timeout=3)
        self.addCleanup(self.client.close)

    def stop_server(self):
        try:
            self.server.stop()
        except Exception:
            pass


class TestServerAndClient(ServerTestCase):

    def test_question_and_answer(self):
        data = self.client.request("where", "Maxima")
        self.assertEqual("Maxima", data["name"])

    def test_several_questions_on_one_connection(self):
        for _ in range(5):
            self.assertEqual("Testville", self.client.request("ping")["town"])
        self.assertEqual("Villa", self.client.request("building", "5,5")["name"])

    def test_numbers_as_arguments(self):
        self.assertEqual(2, len(self.client.request("people", 2)["people"]))

    def test_game_errors_become_exceptions(self):
        with self.assertRaisesRegex(GameError, "no npc named 'Zed'"):
            self.client.request("npc", "Zed")
        # and the connection is still usable
        self.assertEqual("Maxima", self.client.request("where", "Maxima")["name"])

    def test_unknown_command(self):
        with self.assertRaisesRegex(GameError, "unknown command"):
            self.client.request("dance")

    def raw(self, payload:bytes) -> dict:
        with socket.create_connection((self.server.host, self.server.port), timeout=3) as sock:
            sock.sendall(payload)
            return json.loads(sock.makefile("rb").readline())

    def test_garbage_is_answered_not_crashed_on(self):
        for payload in (b"hello\n", b"[1, 2]\n", b'{"cmd": 5}\n', b'{"args": []}\n', b'{"cmd": "world", "args": "x"}\n'):
            with self.subTest(payload=payload):
                answer = self.raw(payload)
                self.assertFalse(answer["ok"])
                self.assertIn("bad request", answer["error"])

        # the game is fine
        self.assertEqual("Testville", self.client.request("ping")["town"])

    def test_broken_query_does_not_hurt_the_server(self):
        from unittest import mock
        with mock.patch.dict("queries.COMMANDS", {"boom": lambda sim, args: 1 / 0}):
            with self.assertRaisesRegex(GameError, "internal error: ZeroDivisionError"):
                self.client.request("boom")
        self.assertEqual("Testville", self.client.request("ping")["town"])

    def test_several_clients_at_once(self):
        clients = [GameClient(port=self.server.port, timeout=3) for _ in range(4)]
        self.addCleanup(lambda: [c.close() for c in clients])
        for client in clients:
            self.assertEqual("Maxima", client.request("where", "max")["name"])

    def test_nothing_to_connect_to(self):
        self.server.stop()
        with self.assertRaises(GameConnectionError):
            GameClient(port=self.server.port, timeout=1).request("ping")

    def test_client_reconnects_after_the_game_restarted(self):
        self.client.request("ping")
        port = self.server.port
        self.server.stop()

        with self.assertRaises(GameConnectionError):
            self.client.request("ping")

        self.server = GameServer(self.sim, port=port)
        self.server.start()
        self.assertEqual("Testville", self.client.request("ping")["town"])

    def test_only_listens_on_this_computer_by_default(self):
        self.assertEqual("127.0.0.1", self.server.host)

    def test_port_in_use(self):
        with self.assertRaises(OSError):
            GameServer(self.sim, port=self.server.port)


class TestWhileTheGameRuns(unittest.TestCase):

    def test_every_snapshot_is_from_one_consistent_moment(self):
        """
        While a phase runs people leave one building before they enter the next.
        If a question could be answered in the middle of a phase somebody would
        be missing everywhere. The lock must prevent that.
        """
        sim = make_sim(extra_citizens=300)
        sim.step()      # now everybody is somewhere

        server = GameServer(sim, port=0)
        server.start()
        self.addCleanup(server.stop)

        runner = threading.Thread(target=lambda: sim.run(6, phase_delay=0.001))
        runner.start()

        client = GameClient(port=server.port, timeout=5)
        self.addCleanup(client.close)
        problems, answers = [], 0
        while runner.is_alive():
            snap = client.request("snapshot", "Maxima")
            answers += 1

            here = sum(b["present"] for b in snap["buildings"]["buildings"])
            alive = snap["world"]["population"]["alive"]
            if here != alive or sum(snap["world"]["census"].values()) != alive:
                problems.append((here, alive, snap["world"]["clock"]))
        runner.join()

        self.assertGreater(answers, 5, "the game must let the server answer while it runs")
        self.assertEqual([], problems)


if __name__ == "__main__":
    unittest.main()
