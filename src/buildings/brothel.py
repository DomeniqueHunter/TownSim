from __future__ import annotations
from typing import TYPE_CHECKING

from .work_building import WorkBuilding

if TYPE_CHECKING:
    from person import Person


class Brothel(WorkBuilding):
    """
    A workplace and the first leisure place of the town. Grown ups can work here
    or come to relax (the entrance costs `price`, the staff pays nothing). Children
    can neither work here nor come in.

    A brothel needs a boss. While it has none (the boss died) it is closed: nobody
    is let in and nobody is paid, until a new boss is appointed.
    """

    def __init__(self, building_name=None, boss:Person=None, work_places:int=10, price:int=10,
                 effects:dict=None):
        if boss is None:
            raise ValueError("a brothel needs a boss")
        if not boss.alive or not boss.is_adult:
            raise ValueError("the boss of a brothel has to be a living grown up")
        if work_places < 1:
            raise ValueError("a brothel needs at least one work place, for the boss")
        if price < 0:
            raise ValueError("the price cannot be negative")

        effects = dict(effects) if effects is not None else {"stamina": 2}
        unknown = set(effects) - {"health", "stamina"}
        if unknown:
            raise ValueError(f"a visit can only change health and stamina, not {sorted(unknown)}")

        WorkBuilding.__init__(self, building_name or "Brothel", boss, work_places)
        self.price = price
        self.effects = effects
        self.visits = 0
        self.revenue = 0

        if not self.employ(boss, "boss"):
            raise ValueError("the boss already works somewhere else")

    @property
    def is_open(self) -> bool:
        return self.boss is not None and self.boss.alive

    @property
    def is_hiring(self) -> bool:
        return self.is_open

    def employ(self, person:Person, role:str="worker") -> bool:
        if not person.is_adult:
            return False
        return WorkBuilding.employ(self, person, role)

    def dismiss(self, person:Person) -> None:
        WorkBuilding.dismiss(self, person)
        if person is self.boss:
            self.boss = None            # no boss: the brothel is closed

    def appoint_boss(self, person:Person) -> None:
        """a new boss, for a brothel that lost its own"""
        if self.is_open:
            raise ValueError(f"{self.name} has a boss already")
        if not person.alive or not person.is_adult:
            raise ValueError("the boss has to be a living grown up")
        if person.workplace is not None and person.workplace is not self:
            raise ValueError("this sim already works somewhere else")

        if person not in self.employees:
            if not self.employ(person, "boss"):
                raise ValueError(f"{self.name} has no free work place for the new boss")
        self.roles[person] = "boss"
        self.boss = person

    def admits(self, person:Person) -> bool:
        """open, grown up, and staff or able to pay the entrance"""
        if not (self.is_open and person.alive and person.is_adult):
            return False
        return person.workplace is self or person.money() >= self.price

    def price_for(self, person:Person) -> int:
        return 0 if person.workplace is self else self.price

    def record_visit(self, paid:int) -> None:
        self.visits += 1
        self.revenue += paid

    def update(self, phase) -> None:
        if self.is_open:            # a closed brothel pays nobody
            WorkBuilding.update(self, phase)

    def __str__(self) -> str:
        return "BR"
