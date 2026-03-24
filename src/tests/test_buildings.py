
from stats import Attributes
from buildings import MegaBuilding, Mansion


def test():
    attr = Attributes(health=(0, 10))
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