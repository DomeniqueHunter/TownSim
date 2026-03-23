
from buildings import HomeBuilding
from stats import Stats


class Mansion(HomeBuilding):
    
    def __init__(self, building_name="Default_Mansion", stories=1, units_per_story=1, persons_per_unit=2, health=100, stamina=100, hunger=3, money=-1000):
        HomeBuilding.__init__(self, building_name, stories, units_per_story, persons_per_unit)
        
        self.gain_stats = Stats(health=health, stamina=stamina, hunger=hunger)
        self.cost_stats = Stats(money=money)
        
    def __str__(self) -> str:
        return "MN" 