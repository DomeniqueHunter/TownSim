from buildings import HomeBuilding
from buildings import WorkBuilding
from buildings import Shop
from buildings import Brothel
from buildings import MegaBuilding
from collections import deque

from .spiral import SpiralGrid
from ledger import Ledger
from graveyard import Graveyard
from items import Catalog


# the town builds a new house when this many of its sims have no home (and none is free) ...
HOMELESS_TO_BUILD = 20
# ... and the house is ready after this many cycles
BUILD_CYCLES = 3
# a new house has this many stories with this many sims per unit, and is free like the first block of the town
NEW_HOUSE_STORIES = 20
NEW_HOUSE_PERSONS_PER_UNIT = 5


class TownHall:
    """
    `grow_jobs`: a grown up who finds every workplace full makes the biggest one bigger by a place
    (without it he has no job and no income).
    `build_houses`: the town builds houses for its homeless (see plan_housing).
    `babies_need_homes`: a baby can only be made while there is a free place for it to live in
    (without it babies can be born homeless and wait for a house).
    """

    def __init__(self, town_name:str, grow_jobs:bool=False, build_houses:bool=False, babies_need_homes:bool=True):
        self.town_name = town_name
        self.grow_jobs = grow_jobs
        self.build_houses = build_houses
        self.babies_need_homes = babies_need_homes
        self.construction = None        # the house that is being built: {"name": ..., "ready": cycle}
        self.houses_built = 0
        self.news = deque(maxlen=100)   # (cycle, text) of what the town did

        self.town_grid = SpiralGrid()
        self.address = self.town_grid.add_next_free(self)

        self.buildings = []

        self.home_buildings = []
        self.work_buildings = []
        self.shop_buildings = []
        self.leisure_buildings = []

        self.citizens = []
        self.ledger = Ledger()
        self.graveyard = Graveyard()
        self.catalog = Catalog()        # all items the town knows
        self.newcomers = []     # citizens who joined since the last cycle ended

    def _tile_is_free(self, pos:tuple) -> bool:
        return pos not in self.town_grid.grid

    def add_building(self, building, tile:tuple=None):
        if building in self.buildings:
            return

        if tile is not None:
            if not self._tile_is_free(tile):
                raise ValueError(f"Tile {tile} is already occupied")
            building.address = self.town_grid.set_grid_field(building, tile)
        else:
            building.address = self.town_grid.add_next_free(building)

        self.buildings.append(building)

        if isinstance(building, HomeBuilding):
            self.home_buildings.append(building)

        if isinstance(building, WorkBuilding):
            self.work_buildings.append(building)

        if isinstance(building, Shop):
            self.shop_buildings.append(building)

        if isinstance(building, Brothel):
            self.leisure_buildings.append(building)

    def add_citizen(self, citizen):
        if citizen not in self.citizens:
            self.citizens.append(citizen)
            self.newcomers.append(citizen)
            citizen.ledger = self.ledger
            citizen.catalog = self.catalog

    def homeless(self) -> list:
        """the living sims who have no home"""
        return [citizen for citizen in self.citizens if citizen.alive and citizen.home is None]

    def house_homeless(self) -> int:
        """gives homes to the homeless where there is room (and they can pay), returns how many found one"""
        homeless = self.homeless()
        if not homeless or not any(b.max_residents > b.residents() for b in self.home_buildings):
            return 0

        homes = self.list_of_buildings()
        return sum(1 for person in homeless if person.find_place_to_live(homes))

    def plan_housing(self, cycle:int) -> None:
        """
        Builds houses for the homeless. When HOMELESS_TO_BUILD sims have no home, even after
        the free places were given out, a house is built (one at a time). It is ready BUILD_CYCLES
        cycles later, appears on the next free field of the town and the homeless move in.
        """
        if not self.build_houses:
            return

        if self.construction is not None:
            if cycle >= self.construction["ready"]:
                self._finish_house(cycle)
            return

        homeless = len(self.homeless())
        if homeless >= HOMELESS_TO_BUILD:
            name = f"Housing {self.houses_built + 1}"
            self.construction = {"name": name, "ready": cycle + BUILD_CYCLES}
            self.news.append((cycle, f"building {name} for {homeless} homeless sims, ready in cycle {cycle + BUILD_CYCLES}"))

    def _finish_house(self, cycle:int) -> None:
        building = MegaBuilding(self.construction["name"], stories=NEW_HOUSE_STORIES,
                                persons_per_unit=NEW_HOUSE_PERSONS_PER_UNIT, health=1, stamina=2, hunger=0, money=0)
        self.add_building(building)
        self.houses_built += 1
        self.construction = None
        moved_in = self.house_homeless()
        self.news.append((cycle, f"{building.name} is ready: {building.max_residents} places, "
                                 f"{moved_in} homeless sims moved in"))

    def free_home_places(self) -> int:
        """places in homes where a sim without money can live (rent 0)"""
        return sum(b.max_residents - b.residents() for b in self.home_buildings if b.rent() == 0)

    def place_newborn(self, baby, mother) -> bool:
        """a baby lives with its mother if there is room in her unit, else somewhere it is free"""
        unit = mother.home
        if unit is not None and unit.has_room() and unit.claim(baby):
            baby.home = unit
            return True
        return baby.find_place_to_live(self.list_of_buildings())

    def integrate_adult(self, person) -> None:
        """
        A grown up gets his shop, a place to relax and, if he has no job, a place at the workplace that
        is emptiest (fewest of its places taken, the first one of the list if equal). That way a place
        that became free, because somebody died, is filled again soon, wherever it is.
        """
        person.find_shop(self.shop_buildings)
        person.find_leisure_spot(self.leisure_buildings)
        if person.workplace is not None:
            return

        openings = [b for b in self.work_buildings if b.is_hiring and len(b.employees) < b.work_places]
        if not openings and self.grow_jobs:
            hiring = [b for b in self.work_buildings if b.is_hiring]
            if hiring:                  # everything is full: the biggest workplace grows by a place
                biggest = max(hiring, key=lambda b: b.work_places)
                biggest.work_places += 1
                openings = [biggest]
        for building in sorted(openings, key=lambda b: len(b.employees) / b.work_places):
            if building.employ(person):
                break

    def collect_newcomers(self) -> list:
        """who joined since the last time this was asked (and forget them)"""
        newcomers, self.newcomers = self.newcomers, []
        return newcomers

    def go_to_address(self, address:str):
        # building, unit = address.split('-')
        # how do we handle business buldings?
        pass

    def remove_dead_citizens(self):
        # drop everybody who died
        self.citizens = [citizen for citizen in self.citizens if citizen.alive]

    def list_of_buildings(self):
        buildings = sorted(self.home_buildings, key=lambda b: b.quality(), reverse=True)
        return buildings

    def __str__(self) -> str:
        return "TH"

    def __repr__(self):
        return f"{self.town_name}: citizens: {len(self.citizens)}, buildings: {len(self.buildings)}"
