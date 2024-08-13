from stats import Stats, Attributes


class Sim:
    
    def __init__(self, *args, attributes=None):
        self.attributes = attributes or Attributes(health=(10,10), stamina=(10,10), hunger=(0,10))
        self.alive = True
        
        self.home = None
        self.workplace = None
        self.current_location = None
    
    def check(self):
        if self.attributes.hunger >= self.attributes.max_hunger+1:
            self.alive = False
            
    def enter_building(self, building):
        self.attributes + building.cost()
        
    def leave_building(self, building):
        self.attributes + building.gain()