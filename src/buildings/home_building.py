
from stats import Stats
from buildings.unit import Unit
import uuid


class HomeBuilding:

    def __init__(self, building_name=None, stories=1, units_per_strory=1, persons_per_unit=2):
        self.name = building_name or str(uuid.uuid4()).replace('-', '')
        self.address = ""   # set by TownHall
        self.gain_stats = Stats()
        self.cost_stats = Stats()
        self.units = {}
        self.persons_per_unit = persons_per_unit

        self.max_residents = len(self.units) * persons_per_unit

        for nr in range(stories * units_per_strory):
            self.units[nr] = Unit(self, nr, self.persons_per_unit)

    def gain(self):
        return int(self.gain_stats)

    def cost(self):
        return int(self.cost_stats)

    def quality(self):
        return self.gain_stats.health + self.gain_stats.stamina + self.gain_stats.hunger - (self.persons_per_unit - 1)

    def get_free_unit(self) -> Unit:
        """
        returns first free unit
        """
        for nr, unit in self.units.items():
            if unit.has_room():
                return unit
        return None

    def get_unit(self, nr):
        if nr in self.units:
            return self.units[nr]
        return None

    def __repr__(self):
        return f"{self.name}: residents: {self.residents()} [{self.quality()}/{self.gain()}/{self.cost()}]"

    def residents(self):
        return sum([unit.residents() for unit in self.units.values()])
