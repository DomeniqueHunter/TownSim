"""
The items folder: drop a JSON file with items into it while the game runs and
the game takes the items over.

A valid file is applied completely (new items for a shop, or gifts for a sim),
then renamed to _consumed_<name>_<timestamp>.json. An invalid file is left
alone, every problem is printed, and it is only looked at again after it was
changed. Files starting with _ or . and files that do not end with .json are
ignored.

The game looks into the folder between two cycles. The items are applied
first, then the state is saved, and only then the file is renamed (see
main.run_cycles), so an interrupted game never loses items.
"""

import os
import time
from pathlib import Path

from items import parse_document
from person import short_name
from queries import find_person, QueryError


MAX_FILE_BYTES = 1_000_000
# a file must be unchanged for this long before it is read (it may still be copied)
STABLE_SECONDS = 1.0
# the folder is looked at this often at the most
MIN_INTERVAL = 0.25


def find_shop(town_hall, name):
    """returns (shop, None) or (None, problem). Without a name it is the first shop."""
    shops = town_hall.shop_buildings
    if not shops:
        return None, "the town has no shop"
    if name is None:
        return shops[0], None

    matches = [shop for shop in shops if shop.name.lower() == name.lower()]
    if len(matches) == 1:
        return matches[0], None
    names = ", ".join(shop.name for shop in shops)
    if not matches:
        return None, f'no shop named "{name}" (shops: {names})'
    return None, f'{len(matches)} shops are named "{name}", rename one of them'


def apply_specs(sim, specs):
    """
    Puts the items of a checked file into the game. Everything is checked
    against the town first, nothing happens if anything is wrong.
    Returns (messages, errors).
    """
    with sim.lock:
        town_hall = sim.town_hall
        known = dict(town_hall.catalog.items)       # what the catalog will look like as we go along
        plan, errors = [], []

        for index, spec in enumerate(specs):
            path = f"items[{index}]"
            shop = person = None

            if spec.deliver_to:
                if spec.stock < 1:
                    errors.append(f"{path}.stock: must be at least 1 when the item is given to a sim")
                try:
                    person = find_person(sim, spec.deliver_to)
                except QueryError as error:
                    errors.append(f"{path}.deliver_to: {error}")
            else:
                shop, problem = find_shop(town_hall, spec.store)
                if problem:
                    errors.append(f"{path}.store: {problem}" if spec.store else f"{path}: {problem}")

            existing = known.get(spec.id)
            if existing is not None and (existing.category != spec.category or existing.effects != spec.effects):
                errors.append(f'{path}: "{spec.id}" already exists as a {existing.category} with the effects '
                              f'{existing.effects}, a new file must keep category and effects')
            else:
                known[spec.id] = spec.definition()

            plan.append((spec, shop, person))

        if errors:
            return [], errors

        messages = []
        for spec, shop, person in plan:
            town_hall.catalog.add(spec.definition())
            if person is not None:
                person.inventory[spec.id] = person.inventory.get(spec.id, 0) + spec.stock
                person.note(None, f"received {spec.stock} {spec.name} as a gift")
                messages.append(f"{spec.name}: {spec.stock} given to {short_name(person.name)}")
            else:
                shop.restock(spec.id, spec.price, spec.stock)
                if spec.stock:
                    messages.append(f"{spec.name}: +{spec.stock} at {shop.name} (price {spec.price})")
                else:
                    messages.append(f"{spec.name}: price at {shop.name} is now {spec.price}")
        return messages, []


class ItemFeed:
    """watches the items folder, see the top of this file"""

    def __init__(self, directory, log=print, clock=time.time,
                 stable_seconds:float=STABLE_SECONDS, min_interval:float=MIN_INTERVAL):
        self.directory = Path(directory)
        self.log = log
        self.clock = clock
        self.stable_seconds = stable_seconds
        self.min_interval = min_interval

        self.seen = {}          # file name -> (size, mtime, when we first saw it like that)
        self.finished = {}      # file name -> (size, mtime) of files we are done with until they change
        self.applied = []       # files that are applied and wait to be renamed
        self.last_scan = None

    def ensure_folder(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def candidates(self) -> list:
        """the files that may contain items"""
        try:
            entries = sorted(os.scandir(self.directory), key=lambda entry: entry.name)
        except OSError:
            return []
        found = []
        for entry in entries:
            name = entry.name
            if name.startswith(("_", ".")) or not name.lower().endswith(".json"):
                continue
            try:
                if entry.is_file():
                    found.append(Path(entry.path))
            except OSError:
                continue
        return found

    def poll(self, sim) -> int:
        """
        Looks at the folder and takes over the files that are ready.
        Returns how many files were applied. Their renaming waits for finish().
        """
        now = self.clock()
        if self.last_scan is not None and now - self.last_scan < self.min_interval:
            return 0
        self.last_scan = now

        applied = 0
        present = set()
        for path in self.candidates():
            present.add(path.name)
            try:
                stat = path.stat()
            except OSError:
                continue
            key = (stat.st_size, stat.st_mtime_ns)

            if self.finished.get(path.name) == key:
                continue
            previous = self.seen.get(path.name)
            if previous is None or previous[:2] != key:
                self.seen[path.name] = (*key, now)      # new or still changing: wait
                self.finished.pop(path.name, None)
                continue
            if now - previous[2] < self.stable_seconds:
                continue

            applied += self.take_over(path, key, sim)

        for name in list(self.seen):                    # forget files that are gone
            if name not in present:
                del self.seen[name]
                self.finished.pop(name, None)
        return applied

    def read(self, path:Path, size:int):
        """returns (text, None) or (None, problem)"""
        if size > MAX_FILE_BYTES:
            return None, f"(file): too large ({size} bytes, at most {MAX_FILE_BYTES})"
        try:
            return path.read_bytes().decode("utf-8-sig"), None
        except UnicodeDecodeError:
            return None, "(file): is not UTF-8 text"
        except OSError as error:
            return None, f"(file): cannot be read: {error}"

    def take_over(self, path:Path, key, sim) -> int:
        text, problem = self.read(path, key[0])
        errors, messages = ([problem], []) if problem else ([], [])
        if not errors:
            specs, errors = parse_document(text)
            if not errors:
                messages, errors = apply_specs(sim, specs)

        self.finished[path.name] = key      # done with it, until somebody changes the file
        if errors:
            self.log(f"items: {path.name} is not valid, nothing was taken over "
                     "(the file stays, change it and it is checked again):")
            for error in errors:
                self.log(f"  {error}")
            return 0

        self.log(f"items: {path.name} taken over:")
        for message in messages:
            self.log(f"  {message}")
        self.applied.append(path)
        return 1

    def finish(self) -> list:
        """renames the applied files to _consumed_<name>_<timestamp>.json, returns the new names"""
        renamed = []
        stamp = int(self.clock())
        for path in self.applied:
            target = path.with_name(f"_consumed_{path.stem}_{stamp}.json")
            number = 2
            while target.exists():
                target = path.with_name(f"_consumed_{path.stem}_{stamp}_{number}.json")
                number += 1
            try:
                path.rename(target)
            except OSError as error:
                self.log(f"items: {path.name} was applied but cannot be renamed ({error}), "
                         "it will not be applied again unless it is changed")
                continue
            renamed.append(target.name)
            self.log(f"items: {path.name} -> {target.name}")
        self.applied = []
        return renamed
