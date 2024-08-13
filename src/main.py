from services import TownHall
from sim import Sim
from stats import Attributes
import math
from home_building import MegaBuilding, Mansion


def main():
    town_hall = TownHall("Small Ville")
    
    minimus = Sim(name="Minimus")
    maxima = Sim(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))
    
    town_hall.add_citizen(minimus)
    town_hall.add_citizen(maxima)
    
    poverty_building = MegaBuilding("Poverty 1", stories=100, sims_per_unit=10, health=1, stamina=2, hunger=0, money=0)
    # poverty_building_test = MegaBuilding(None, stories=100, sims_per_unit=10, health=1, stamina=2, hunger=0, money=0)
    mb = MegaBuilding("Mega Block 1")
    mansion = Mansion("Villa Maxima")
    
    town_hall.add_building(poverty_building)
    town_hall.add_building(mb)
    town_hall.add_building(mansion)
    
    print(town_hall)
    
    for sim in town_hall.citizens:
        sim.find_place_to_live(town_hall)
        sim.go(sim.home)
    
    print()
    for building in town_hall.home_buildings:
        print(building)
    
    print() 
    print(maxima, maxima.current_location)
    print(minimus, minimus.current_location)


if __name__ == "__main__":
    main()
