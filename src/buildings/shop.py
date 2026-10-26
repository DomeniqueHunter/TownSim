from __future__ import annotations
import math
from typing import TYPE_CHECKING

from items import BUILTIN_FOOD
from stats import Stats
from .work_building import WorkBuilding

if TYPE_CHECKING:
    from person import Person


class Offer:
    """
    One thing a shop has for sale: what a piece costs and how many pieces are left.

    The shop does not hold a million bottles, it holds a number. A delivery is counted in units
    (litres, say) and is split into pieces of `portion` units, whatever does not make a whole piece
    waits in `loose` for the next delivery. `quantity` is the number of whole pieces.
    """

    def __init__(self, item_id:str, price:int, quantity:float, portion:int=1, loose:int=0):
        self.item_id = item_id
        self.price = price
        self.quantity = quantity        # pieces that can be bought, math.inf: never runs out
        self.portion = portion          # units in one piece
        self.loose = loose              # units that are not enough for a piece yet

    @property
    def units(self) -> float:
        """everything that is left, in units"""
        return self.quantity if self.quantity == math.inf else self.quantity * self.portion + self.loose

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
                 default_food:bool=True, food_per_cycle:int=None):
        WorkBuilding.__init__(self, building_name or "Shop", boss, work_places)
        self.stock = {}                 # item id -> Offer
        self.revenue = 0
        self.sold = 0                   # pieces sold, of everything
        self.food_per_cycle = food_per_cycle    # None: the plain food never runs out

        if default_food:
            quantity = math.inf if food_per_cycle is None else food_per_cycle
            self.stock[BUILTIN_FOOD.id] = Offer(BUILTIN_FOOD.id, food_price, quantity)

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

    def supply(self, phase_index:int, phases:int=10) -> int:
        """
        The daily ration of plain food (food_per_cycle) arrives in equal parts over the phases of the day,
        so every group of sims finds the same on the shelf. The shelf holds one ration at the most (what is not
        bought goes bad), but stock that was delivered in files above that is left alone.
        Returns the number of pieces that arrived.
        """
        offer = self.stock.get(BUILTIN_FOOD.id)
        if self.food_per_cycle is None or offer is None:
            return 0

        ration = self.food_per_cycle
        arriving = ration * (phase_index + 1) // phases - ration * phase_index // phases
        if offer.quantity < ration:
            offer.quantity = min(offer.quantity + arriving, ration)
        return arriving

    def restock(self, item_id:str, price:int, amount:int, portion:int=1) -> Offer:
        """
        Puts a delivery of `amount` units on the shelf, split into pieces of `portion` units
        (the price is per piece). A new item is added, for an item the shop has already the
        price is replaced and the delivery is added to what is there (the portion cannot change).
        """
        offer = self.stock.get(item_id)
        if offer is None:
            offer = self.stock[item_id] = Offer(item_id, price, 0, portion)
        elif offer.portion != portion:
            raise ValueError(f"{item_id} is sold in pieces of {offer.portion} units here, not {portion}")

        offer.price = price
        if offer.quantity != math.inf:          # a shelf that never runs out stays that way
            pieces, offer.loose = divmod(offer.loose + amount, portion)
            offer.quantity += pieces
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
