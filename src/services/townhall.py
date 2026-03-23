from buildings import HomeBuilding


class TownHall:
    
    def __init__(self, town_name:str):
        self.town_name = town_name

        self.town_map = {(0,0): self}
        
        self.buildings = []

        self.home_buildings = []
        self.work_buildings = []
        self.leisure_buildings = []
        
        self.citizens = []

    def __check_tile(self, pos:tuple) -> bool:
        tile = self.town_map.get(pos, None)
        if tile == None: return True
        return False
        
    def add_building(self, building, tile:tuple=None):
        # TODO:
        # if not tile, get closes free tile to the TownHall
        # if tile it set, check if free, if not return False

        if building not in self.buildings:
            self.buildings.append(building)
            # TODO: set address
            
            if isinstance(building, HomeBuilding):
                self.home_buildings.append(building)

            # if isinstance(building, WorkBuilding):
            #     self.work_buildings.append(building)

            # TODO leisure
            # if isinstance(building, LeisureBuilding):
            #     self.leisure_buildings.append(building)
            
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
    
    
        
