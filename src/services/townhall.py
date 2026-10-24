from buildings import HomeBuilding
from buildings import WorkBuilding
from buildings import Shop
from buildings import Brothel
from .spiral import SpiralGrid
from ledger import Ledger
from graveyard import Graveyard
from items import Catalog


class TownHall:

    def __init__(self, town_name:str):
        self.town_name = town_name

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
