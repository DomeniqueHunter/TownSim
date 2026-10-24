from __future__ import annotations
from typing import TYPE_CHECKING

from .building import Building

if TYPE_CHECKING:
    from person import Person


# money per day of work
WAGES = {"boss": 100, "office": 50, "worker": 25}


class WorkBuilding(Building):

    def __init__(self, building_name=None, boss:Person=None, work_places:int=10):
        Building.__init__(self)
        self.building_name = building_name
        self.name = building_name or "Work Building"
        self.address = ""   # set by TownHall

        self.boss = boss
        self.work_places = work_places
        self.employees = []
        self.roles = {}     # person -> "office" / "worker", everybody else is a worker

    @property
    def is_hiring(self) -> bool:
        """whether new staff makes sense here (a closed brothel pays nobody)"""
        return True

    def employ(self, person:Person, role:str="worker") -> bool:
        """
        hires the person, returns False if there is no place left, or the person already has
        this job or another one (dismiss first to change jobs)
        """
        if role not in WAGES:
            raise ValueError(f"unknown role {role!r}, use one of {list(WAGES)}")

        if person in self.employees or len(self.employees) >= self.work_places:
            return False
        if person.workplace is not None and person.workplace is not self:
            return False

        self.employees.append(person)
        self.roles[person] = role
        person.workplace = self
        return True

    def dismiss(self, person:Person) -> None:
        if person in self.employees:
            self.employees.remove(person)
        self.roles.pop(person, None)
        if person.workplace is self:
            person.workplace = None

    def wage_for(self, person:Person) -> int:
        if person is self.boss:
            return WAGES["boss"]
        return WAGES[self.roles.get(person, "worker")]

    def update(self, phase) -> None:
        """
        The daily business: everybody who is here and works in this phase
        earns his wage (each routine has exactly one work phase per day).
        """
        for person in self.currently_here:
            if person.workplace is self and person.is_working(phase):
                person.earn(self.wage_for(person), phase, self.name)

    def __str__(self) -> str:
        return "WB"
