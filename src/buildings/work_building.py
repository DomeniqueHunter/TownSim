


class WorkBuilding:

    def __init__(self, building_name=None, boss:"Person", work_places:int):
        self.building_name = building_name
        self.address = ""   # set by TownHall

        self.boss = boss
        self.work_places = work_places
        self.employees = []

    def self.employ(self, person:"Person"):
        if not person in self.employees and len(self.employees) < self.work_places:
            self.employees.append(person)
            person.workplace = self
