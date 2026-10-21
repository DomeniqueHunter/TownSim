"""
The wire format between the game and its clients (console.py, display.py).

One request per line, one answer per line, both JSON:

    -> {"cmd": "npc", "args": ["Maxima"]}
    <- {"ok": true,  "data": {...}}
    <- {"ok": false, "error": "no npc named 'Maxim'"}

This file must not import anything from the game, so the clients stay light.
"""

import json

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7777

MAX_LINE = 1_000_000


def encode(message:dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def decode(line:bytes) -> dict:
    return json.loads(line.decode("utf-8"))
