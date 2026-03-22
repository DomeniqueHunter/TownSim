class Unit:
    
    def __init__(self, building, unit_number:int, max_persons=2):
        self.building = building
        self.unit_number = unit_number 
        self.max_persons = max_persons
        self.owners = []
        self.currently_here = []
        
    def has_room(self):
        return len(self.owners) < self.max_persons
    
    def address(self):
        return f"{self.building.name}-{self.unit_number}"
    
    def claim(self, person):
        if person not in self.owners:
            self.owners.append(person)
            return True
        return False
    
    def location_stats(self):
        return self.building.gain_stats + self.building.cost_stats
    
    def enter(self, person):
        if person not in self.currently_here:
            self.currently_here.append(person)
            person.current_location = self
            return True 
        return False
    
    def leave(self, person):
        if person in self.currently_here:
            self.currently_here.remove(person)
            return True
        return False
    
    def residents(self):
        return len(self.owners)
    
    def __repr__(self):
        return f"{self.building.name}-{self.unit_number}"