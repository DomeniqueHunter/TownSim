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
    
    def leave(self, sim):
        if sim in self.currently_here:
            self.currently_here.remove(sim)
            return True
        return False
    
    def residents(self):
        return len(self.owners)
    
    def __repr__(self):
        return f"{self.building.name}-{self.unit_number}"