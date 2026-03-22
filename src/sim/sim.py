from stats import Stats, Attributes

import uuid
import math
from services import TownHall


class Sim:
    
    def __init__(self, *args, name:str=None, attributes:Attributes=None):
        self.attributes = attributes or Attributes(health=(10, 10), stamina=(10, 10), hunger=(0, 10))
        self.name = name or uuid.uuid4()  # maybe not a nice name but we will see
        
        self.alive = True
        
        self.home = None
        self.workplace = None
        self.current_location = None
        
    def interactions(self) -> list["str"]:
        possible_interactions = ["give"]
        
        if self.current_location == self.home:
            possible_interactions += ["fuck"]
        elif self.current_location == self.workplace:
            possible_interactions += ["work"]
        else:
            possible_interactions += ["goto"]
        
        return possible_interactions
    
    def interact_with(self, other:"Sim"):
        pass
    
    def money(self):
        return self.attributes.money
    
    def check(self, verbose=False):
        if self.attributes.hunger == self.attributes.max_hunger:
            self.alive = False
            self.die(verbose=verbose)
            
        return self.alive
            
    def die(self, verbose=False):
        if verbose: print(f"sim: {self.name} died")
        if self.current_location:
            self.current_location.leave(self)
        
        if self.home:
            self.home.owners.remove(self)
            self.home = None
    
    def apply_location(self):
        if self.current_location:
            self.attributes += self.current_location.location_stats()
    
    def find_place_to_live(self, town_hall:TownHall):
        buildings = town_hall.list_of_buildings()
        
        for building in buildings:
            # print(home_building.name, home_building.quality(), home_building.cost())
            if self.money() >= abs(building.cost()):
                unit = building.get_free_unit()
                if unit.claim(self):
                    self.home = unit
                    break
                
    def go(self, location):
        if location:
            return location.enter(self)
        
    def __repr__(self):
        return f"{self.name}: {self.home} ({self.attributes})"


def main():
    sim = Sim(name="Minimus")
    mega_sim = Sim(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))
    
    print(sim, sim.money())
    print(mega_sim, mega_sim.money())
            
        
if __name__ == "__main__":
    main()
