
from stats import Stats
from .building import Building
from .unit import Unit

import uuid


class HomeBuilding(Building):

    def __init__(self, building_name=None, stories=1, units_per_story=1, persons_per_unit=2):
        Building.__init__(self)
        self.name = building_name or str(uuid.uuid4()).replace('-', '')
        self.address = ""   # set by TownHall
        self.gain_stats = Stats()
        self.cost_stats = Stats()
        self.persons_per_unit = persons_per_unit

        self.units = {}
        for nr in range(stories * units_per_story):
            self.units[nr] = Unit(self, nr, self.persons_per_unit)

    @property
    def max_residents(self):
        return len(self.units) * self.persons_per_unit

    def gain(self):
        return int(self.gain_stats)

    def cost(self):
        return int(self.cost_stats)

    def rent(self):
        """
        Money a person needs to live here.
        Costs are stored as negative money in cost_stats (e.g. money=-1000).
        """
        return max(0, -self.cost_stats.money)

    def quality(self):
        return self.gain_stats.health + self.gain_stats.stamina + self.gain_stats.hunger - (self.persons_per_unit - 1)

    def get_free_unit(self) -> Unit | None:
        """
        returns first free unit (or None if the building is full)
        """
        for nr, unit in self.units.items():
            if unit.has_room():
                return unit
        return None

    def get_unit(self, nr):
        if nr in self.units:
            return self.units[nr]
        return None

    def __str__(self)->str:
        return "HB"

    def __repr__(self):
        return f"{self.name}: residents: {self.residents()}/{self.max_residents} [{self.quality()}/{self.gain()}/{self.cost()}]"

    def residents(self):
        return sum([unit.residents() for unit in self.units.values()])
