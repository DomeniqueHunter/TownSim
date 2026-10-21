from __future__ import annotations
from typing import TYPE_CHECKING

from stats import Stats
from .work_building import WorkBuilding

if TYPE_CHECKING:
    from person import Person


class Shop(WorkBuilding):
    """
    People buy food here (and can work here, like in any WorkBuilding).
    The stock is unlimited for now.
    """

    def __init__(self, building_name=None, boss:Person=None, work_places:int=10, food_price:int=5):
        WorkBuilding.__init__(self, building_name or "Shop", boss, work_places)
        self.food_price = food_price
        self.revenue = 0
        self.sold = 0

    def sell_food(self, person:Person, amount:int) -> int:
        """
        Sells up to `amount` food to the person, as much as he can afford.
        The food ends up in the persons inventory. Returns the amount sold.
        """
        if amount <= 0:
            return 0

        if self.food_price > 0:
            amount = int(min(amount, person.money() / self.food_price))
            if amount <= 0:
                return 0

        cost = amount * self.food_price
        person.attributes += Stats(money=-cost)
        person.inventory["food"] += amount
        self.revenue += cost
        self.sold += amount
        return amount

    def __str__(self) -> str:
        return "SH"
