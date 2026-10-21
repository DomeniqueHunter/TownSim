"""
Talks to a running game. Used by console.py and display.py.
Knows nothing about the game itself, only the protocol.
"""

import socket

import protocol


class GameError(Exception):
    """the game understood the question but cannot answer it (unknown npc, ...)"""


class GameConnectionError(Exception):
    """there is no game to talk to"""


class GameClient:

    def __init__(self, host:str=protocol.DEFAULT_HOST, port:int=protocol.DEFAULT_PORT, timeout:float=5.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None
        self.reader = None

    def connect(self) -> None:
        self.close()
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as error:
            raise GameConnectionError(
                f"cannot connect to the game at {self.host}:{self.port} ({error}). Is main.py running?") from error
        self.reader = self.sock.makefile("rb")

    def close(self) -> None:
        for resource in (self.reader, self.sock):
            if resource is not None:
                try:
                    resource.close()
                except OSError:
                    pass
        self.sock = self.reader = None

    def _exchange(self, payload:bytes) -> bytes:
        if self.sock is None:
            self.connect()
        self.sock.sendall(payload)
        line = self.reader.readline(protocol.MAX_LINE)
        if not line:
            raise ConnectionError("the game closed the connection")
        return line

    def request(self, cmd:str, *args):
        """asks one question, returns the answer data"""
        payload = protocol.encode({"cmd": cmd, "args": [str(arg) for arg in args]})

        try:
            line = self._exchange(payload)
        except (OSError, ConnectionError):
            # the connection may be stale (game restarted), try once with a new one
            self.close()
            try:
                line = self._exchange(payload)
            except (OSError, ConnectionError) as error:
                self.close()
                raise GameConnectionError(
                    f"lost the connection to the game at {self.host}:{self.port} ({error})") from error

        answer = protocol.decode(line)
        if not answer.get("ok"):
            raise GameError(answer.get("error", "unknown error"))
        return answer["data"]
