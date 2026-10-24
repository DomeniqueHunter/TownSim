import os
import pickle
import random
import tempfile
from pathlib import Path


SAVE_VERSION = 10


class SaveError(Exception):
    """the save file is missing, damaged or from an incompatible version"""


def save_state(simulation, path) -> None:
    """
    Writes the whole simulation (town, buildings, citizens, clock, random state)
    to `path`. The file is written to a temp file first and then moved into
    place, so a crash or Ctrl+C while saving never destroys the previous save.
    """
    path = Path(path)
    data = {
        "version": SAVE_VERSION,
        "simulation": simulation,
        "random_state": random.getstate(),
    }

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp:
            pickle.dump(data, tmp, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_state(path):
    """returns the Simulation stored in `path` and restores the random state"""
    path = Path(path)

    try:
        with open(path, "rb") as file:
            data = pickle.load(file)
    except FileNotFoundError:
        raise
    except Exception as error:
        raise SaveError(f"cannot read save file {path}: {error}") from error

    if not isinstance(data, dict) or data.get("version") != SAVE_VERSION:
        raise SaveError(f"{path} is not a compatible save file (expected version {SAVE_VERSION})")

    random.setstate(data["random_state"])
    return data["simulation"]
