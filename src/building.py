# from stats import Stats, Attributes
from town_sim.src.stats import Attributes, Stats


class Building:
    
    def __init__(self):
        self.gain_stats = Stats()
        self.cost_stats = Stats()
    
    def gain(self):
        return self.gain_stats 
    
    def cost(self):
        return self.cost_stats


class Unit:
    
    def __init__(self, number):
        self.number = number 
        self.owners = []
        self.currently_here = []


class MegaBuilding(Building):
    
    def __init__(self, stories=1, units_per_strory=1):
        Building.__init__(self)
        
        self.gain_stats = Stats(health=10, stamina=10)
        self.cost_stats = Stats(money=-1)
        
        self.units = {}
        for nr in range(stories * units_per_strory):
            self.units[nr] = Unit(nr)
            
    def get_unit(self, nr):
        if nr in self.units:
            return self.units[nr]
        return None
    
    
def test():
    attr = Attributes(health=(50, 100), money=5)
    print(attr)
    
    mb = MegaBuilding()
    attr + mb.gain() + mb.cost()
    print(attr)
    
    
if __name__ == "__main__":
    test()
