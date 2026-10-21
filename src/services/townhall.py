from buildings import HomeBuilding
from buildings import WorkBuilding
from buildings import Shop
from .spiral import SpiralGrid
from ledger import Ledger
from graveyard import Graveyard


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

        # TODO leisure
        # if isinstance(building, LeisureBuilding):
        #     self.leisure_buildings.append(building)

    def add_citizen(self, citizen):
        if citizen not in self.citizens:
            self.citizens.append(citizen)
            self.newcomers.append(citizen)
            citizen.ledger = self.ledger

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
