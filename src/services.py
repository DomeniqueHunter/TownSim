from home_building import HomeBuilding


class TownHall:
    
    def __init__(self, town_name:str):
        self.town_name = town_name
        
        self.buildings = []
        self.home_buildings = []
        
        self.citizens = []
        
    def add_building(self, building):
        if building not in self.buildings:
            self.buildings.append(building)
            
            if isinstance(building, HomeBuilding):
                self.home_buildings.append(building)
            
    def add_citizen(self, citizen):
        if citizen not in self.citizens:
            self.citizens.append(citizen)
            
    def go_to_address(self, address:str):
        # building, unit = address.split('-')
        # how do we handle business buldings?
        pass
            
    def _maintain_citizens(self):        
        for citizen in self.citizens:
            if not self.citizens.alive:
                self.citizens.remove(citizen)
            
    def list_of_buildings(self):        
        buildings = sorted(self.home_buildings, key=lambda b: b.quality(), reverse=True)
        return buildings
    
    def __repr__(self):
        return f"{self.town_name}: citizens: {len(self.citizens)}, buildings: {len(self.buildings)}"
    
    
        
