import socket
import socketserver
import threading

import protocol
import queries


class _Handler(socketserver.StreamRequestHandler):

    timeout = 60    # drop clients that went silent

    def setup(self):
        super().setup()
        self.server.add_connection(self.request)

    def finish(self):
        self.server.remove_connection(self.request)
        super().finish()

    def handle(self):
        while True:
            try:
                line = self.rfile.readline(protocol.MAX_LINE)
            except OSError:
                return
            if not line:
                return

            self.wfile.write(protocol.encode(self.answer(line)))
            self.wfile.flush()

    def answer(self, line:bytes) -> dict:
        try:
            request = protocol.decode(line)
            cmd, args = request["cmd"], request.get("args", [])
            if not isinstance(cmd, str) or not isinstance(args, list):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return {"ok": False, "error": 'bad request, expected {"cmd": "...", "args": [...]}'}

        try:
            return {"ok": True, "data": queries.run(self.server.sim, cmd, args)}
        except queries.QueryError as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:   # a broken query must never hurt the game
            return {"ok": False, "error": f"internal error: {type(error).__name__}: {error}"}


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.connections = set()
        self.connections_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def add_connection(self, connection):
        with self.connections_lock:
            self.connections.add(connection)

    def remove_connection(self, connection):
        with self.connections_lock:
            self.connections.discard(connection)

    def close_connections(self):
        with self.connections_lock:
            connections = list(self.connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class GameServer:
    """
    Lets other programs (console.py, display.py) ask questions about the running
    simulation. Only listens on this computer by default and only answers
    read-only questions, nothing can be changed through it.
    """

    def __init__(self, sim, host:str=protocol.DEFAULT_HOST, port:int=protocol.DEFAULT_PORT):
        self.server = _Server((host, port), _Handler)
        self.server.sim = sim
        self.host, self.port = self.server.server_address[:2]   # port 0 -> the one that was picked
        self.thread = None

    def start(self) -> None:
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.05),
                                       name="game-server", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """stops listening and hangs up on everybody who is connected"""
        self.server.shutdown()
        self.server.server_close()
        self.server.close_connections()
        if self.thread:
            self.thread.join(timeout=5)
