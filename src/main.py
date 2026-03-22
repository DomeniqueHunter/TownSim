from services import TownHall
from sim import Sim
from stats import Attributes, Stats
import math
from buildings import MegaBuilding, Mansion


def main():
    town_hall = TownHall("Small Ville")
    
    minimus = Sim(name="Minimus", attributes=Attributes(money=100))
    maxima = Sim(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))
    
    for _ in range(1000):
        town_hall.add_citizen(Sim())
    
    town_hall.add_citizen(minimus)
    town_hall.add_citizen(maxima)
    
    poverty_building = MegaBuilding("Mega Poverty 1", stories=100, sims_per_unit=10, health=1, stamina=2, hunger=0, money=0)
    mb = MegaBuilding("Mega Block 1", stories=15, sims_per_unit=3, health=2, stamina=3, money=2)
    mansion = Mansion("Villa Maxima", health=5, stamina=10, hunger=-3)
    
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
    
    round_malus = Stats(hunger=1)
    
    print()
    for _ in range(12):
        for citizen in town_hall.citizens:
            if not citizen.alive: continue
            
            # apply location stats
            citizen.apply_location()
            
            # round end
            citizen.attributes += round_malus
            
            # check if citizen is alive
            if not citizen.check():
                citizen.die()
            
    print(maxima, maxima.current_location)
    print(minimus, minimus.current_location)
    
    print(mansion)
    print(mb)
    print(poverty_building)


if __name__ == "__main__":
    main()
