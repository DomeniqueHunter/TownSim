from __future__ import annotations
import math
from typing import TYPE_CHECKING

from items import BUILTIN_FOOD
from stats import Stats
from .work_building import WorkBuilding

if TYPE_CHECKING:
    from person import Person


class Offer:
    """one thing a shop has for sale: how much it costs and how many pieces are left"""

    def __init__(self, item_id:str, price:int, quantity:float):
        self.item_id = item_id
        self.price = price
        self.quantity = quantity        # math.inf: never runs out

    def __repr__(self):
        return f"Offer({self.item_id}, price {self.price}, {self.quantity} left)"


class Shop(WorkBuilding):
    """
    People buy things here (and can work here, like in any WorkBuilding).

    Every shop starts with the plain food of the game at `food_price`, which
    never runs out. Items from files (see itemfeed.py) are added with
    `restock`. `default_food=False` makes a shop that starts empty.
    """

    def __init__(self, building_name=None, boss:Person=None, work_places:int=10, food_price:int=5,
                 default_food:bool=True):
        WorkBuilding.__init__(self, building_name or "Shop", boss, work_places)
        self.stock = {}                 # item id -> Offer
        self.revenue = 0
        self.sold = 0                   # pieces sold, of everything

        if default_food:
            self.stock[BUILTIN_FOOD.id] = Offer(BUILTIN_FOOD.id, food_price, math.inf)

    @property
    def food_price(self):
        """price of the plain food, None if the shop does not sell it"""
        offer = self.stock.get(BUILTIN_FOOD.id)
        return offer.price if offer else None

    @food_price.setter
    def food_price(self, price:int) -> None:
        offer = self.stock.get(BUILTIN_FOOD.id)
        if offer is None:
            raise ValueError("this shop does not sell the plain food")
        offer.price = price

    def restock(self, item_id:str, price:int, quantity:int) -> Offer:
        """
        Puts `quantity` pieces on the shelf. A new item is added, for an item
        the shop has already the price is replaced and the pieces are added.
        """
        offer = self.stock.get(item_id)
        if offer is None:
            offer = self.stock[item_id] = Offer(item_id, price, 0)
        offer.price = price
        offer.quantity += quantity
        return offer

    def sell(self, person:Person, item_id:str, amount:int) -> int:
        """
        Sells up to `amount` pieces, as many as the person can afford and the
        shop has. They end up in the persons inventory. Returns the amount sold.
        """
        offer = self.stock.get(item_id)
        if offer is None or amount <= 0:
            return 0

        amount = min(amount, offer.quantity)
        if offer.price > 0:
            amount = min(amount, person.money() / offer.price)
        amount = int(amount)
        if amount <= 0:
            return 0

        cost = amount * offer.price
        person.attributes += Stats(money=-cost)
        person.inventory[item_id] = person.inventory.get(item_id, 0) + amount
        offer.quantity -= amount
        self.revenue += cost
        self.sold += amount
        return amount

    def sell_food(self, person:Person, amount:int) -> int:
        """sells the plain food"""
        return self.sell(person, BUILTIN_FOOD.id, amount)

    def __str__(self) -> str:
        return "SH"
