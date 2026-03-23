
from buildings import Building
from person import Person


class WorkBuilding(Building):

    def __init__(self, building_name=None, boss:Person=None, work_places:int=10):
        Building.__init__(self)
        self.building_name = building_name
        self.address = ""   # set by TownHall

        self.boss = boss
        self.work_places = work_places
        self.employees = []

    def employ(self, person:Person):
        if not person in self.employees and len(self.employees) < self.work_places:
            self.employees.append(person)
            person.workplace = self
            
    def __str__(self) -> str:
        return "WB"
