
from .home_building import HomeBuilding
from stats import Stats


class MegaBuilding(HomeBuilding):

    def __init__(self, building_name="Default_MegaBuilding", stories=1, units_per_story=1, persons_per_unit=5, health=10, stamina=10, hunger=0, money=-1):
        HomeBuilding.__init__(self, building_name, stories, units_per_story, persons_per_unit)

        self.gain_stats = Stats(health=health, stamina=stamina, hunger=hunger)
        self.cost_stats = Stats(money=money)

    def __str__(self) -> str:
        return "MB"
