from stats import Stats, Attributes
import uuid


class Unit:
    
    def __init__(self, building, unit_number:int, max_sims=2):
        self.building = building
        self.unit_number = unit_number 
        self.max_sims = max_sims
        self.owners = []
        self.currently_here = []
        
    def has_room(self):
        return len(self.owners) < self.max_sims
    
    def address(self):
        return f"{self.building.name}-{self.unit_number}"
    
    def claim(self, sim):
        if sim not in self.owners:
            self.owners.append(sim)
            return True
        return False
    
    def location_stats(self):
        return self.building.gain_stats + self.building.cost_stats
    
    def enter(self, sim):
        if sim not in self.currently_here:
            self.currently_here.append(sim)
            sim.current_location = self
            return True 
        return False
    
    def __repr__(self):
        return f"{self.building.name}-{self.unit_number}"


class HomeBuilding:
    
    def __init__(self, building_name=None, stories=1, units_per_strory=1, sims_per_unit=2):
        self.name = building_name or str(uuid.uuid4()).replace('-', '')
        self.gain_stats = Stats()
        self.cost_stats = Stats()
        self.units = {}
        self.sims_per_unit = sims_per_unit
        
        for nr in range(stories * units_per_strory):
            self.units[nr] = Unit(self, nr, self.sims_per_unit)
    
    def gain(self):
        return int(self.gain_stats) 
    
    def cost(self):
        return int(self.cost_stats)
    
    def quality(self):
        return self.gain_stats.health + self.gain_stats.stamina + self.gain_stats.hunger - (self.sims_per_unit - 1)
    
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
        return f"{self.name}: {self.quality()}/{self.gain()}/{self.cost()}"


class MegaBuilding(HomeBuilding):
    
    def __init__(self, building_name="Default_MegaBuilding", stories=1, units_per_strory=1, sims_per_unit=5, health=10, stamina=10, hunger=0, money=-1):
        HomeBuilding.__init__(self, building_name, stories, units_per_strory, sims_per_unit)
        
        self.gain_stats = Stats(health=health, stamina=stamina, hunger=hunger)
        self.cost_stats = Stats(money=money)
        
    
class Mansion(HomeBuilding):
    
    def __init__(self, building_name="Default_Mansion", stories=1, units_per_story=1, sims_per_unit=2, health=100, stamina=100, hunger=3, money=-1000):
        HomeBuilding.__init__(self, building_name, stories, units_per_story, sims_per_unit)
        
        self.gain_stats = Stats(health=health, stamina=stamina, hunger=hunger)
        self.cost_stats = Stats(money=money)

    
def test():
    attr = Attributes(health=(0, 10), money=0)
    print(attr)
    
    mb = MegaBuilding()
    attr + mb.gain() + mb.cost()
    print(attr)
    print(mb.quality())
    
    mansion = Mansion("Mansion Maxima")
    print(mansion)
    unit = mansion.get_unit(0)
    print(unit, unit.location_stats())
    
    
if __name__ == "__main__":
    test()
