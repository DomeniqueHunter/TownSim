from services import TownHall
from person import Person, maxima
from stats import Attributes, Stats
from buildings import MegaBuilding, Mansion, Tile


def main():
    town_hall = TownHall("Small Ville")
    
    minimus = Person(name="Minimus")
    minimus.attributes + Stats(money=100)
    # maxima = Person(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))
    
    for _ in range(1000):
        town_hall.add_citizen(Person())
    
    town_hall.add_citizen(minimus)
    town_hall.add_citizen(maxima)
    
    poverty_building = MegaBuilding("Mega Poverty 1", stories=100, persons_per_unit=10, health=1, stamina=2, hunger=0, money=0)
    mb = MegaBuilding("Mega Block 1", stories=15, persons_per_unit=3, health=2, stamina=3, money=2)    
    mansion = Mansion("Villa Maxima", health=5, stamina=10, hunger=-3)
    
    town_hall.add_building(poverty_building)
    town_hall.add_building(mb)
    town_hall.add_building(mansion, (5,5))
    
    town_hall.add_building(Tile("Grass Land", "GL"), (-5,-5))
    town_hall.add_building(Tile("Grass Land", "GL"), (-10,-10))
    town_hall.add_building(Tile("Grass Land", "GL"), (10,10))
    town_hall.add_building(Tile("Grass Land", "GL"), (10,0))
    
    print(town_hall)
    
    for person in town_hall.citizens:
        person.find_place_to_live(town_hall.list_of_buildings())
        person.go(person.home)
    
    print()
    for building in town_hall.home_buildings:
        print(building)
    
    print() 
    print(maxima, maxima.current_location)
    print(minimus, minimus.current_location)
    
    round_malus = Stats(hunger=1)
    
    print()
    for _ in range(10):
        for citizen in town_hall.citizens:
            if not citizen.alive: continue
            
            # apply location stats
            citizen.apply_location()
            
            # round end
            citizen.attributes += round_malus
            
            # check if citizen is alive
            citizen.check()

            
    print(maxima, maxima.current_location)
    print(minimus, minimus.current_location)
    print(minimus.alive)
    
    # print(mansion)
    # print(mb)
    # print(poverty_building)
    #
    # print(town_hall.town_grid.grid)
    # town_hall.town_grid.show()


if __name__ == "__main__":
    main()
