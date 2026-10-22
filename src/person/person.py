from __future__ import annotations
from stats import Stats, Attributes
from .routine import routines, DayTime, ActionType

import uuid
import math
import random
from collections import Counter, deque
from typing import NamedTuple


# a person tries to keep this many food items in the inventory
FOOD_STOCK_TARGET = 3
# one food item reduces hunger by this much
FOOD_RELIEF = 1
# sims eat at home when they wake up and when they get back home
MEAL_ACTIONS = (ActionType.WAKEUP, ActionType.GO_HOME)
# every sim gets a random lifespan (in cycles) from this range, both ends included
LIFESPAN_RANGE = (90, 110)
# from this age on a sim is grown up: it gets a job, buys its own food and gets hungry.
# Younger sims (children) stay at home and are fed by the household.
ADULT_AGE = 18
# only sims of these ages can mate (both ends included)
FERTILE_AGES = (18, 50)


class Pregnancy(NamedTuple):
    due_cycle: int      # the baby is born at the end of this cycle
    partner: "Person"   # the other parent


def short_name(name) -> str:
    """names of sims can be long (uuid), texts show the first 8 characters"""
    return str(name)[:8]


class Person:

    def __init__(self, *args, name:str=None, attributes:Attributes=None, routine:int=None,
                 age:int=ADULT_AGE, lifespan:float=None, parents:tuple=None):
        """
        `age` is counted in cycles, without one the sim is grown up (ADULT_AGE),
        new born sims are made with age=0. The sim dies of old age when its age
        reaches `lifespan`. Without a lifespan a random one from LIFESPAN_RANGE is
        picked, math.inf means the sim never dies of old age.
        `parents` are the names of the two parents (None for the first sims).
        """
        if age < 0:
            raise ValueError("age cannot be negative")
        if lifespan is not None and lifespan <= 0:
            raise ValueError("lifespan must be positive")

        self.attributes = attributes or Attributes(health=(10, 10), stamina=(10, 10), hunger=(0, 10))
        self.name = name or str(uuid.uuid4())  # maybe not a nice name but we will see

        self.alive = True
        self.cause_of_death = None

        self.age = age
        self.lifespan = lifespan if lifespan is not None else random.randint(*LIFESPAN_RANGE)

        self.parents = parents      # names of the two parents, None for the first sims
        self.children = 0           # how many children the sim has had
        self.pregnancy = None       # a Pregnancy while a baby is on its way

        self.inventory = {"food": 0}

        self.ledger = None          # set by the TownHall when the person becomes a citizen
        self.totals = Counter()     # lifetime: food_bought, food_eaten, money_spent, money_earned
        self.log = deque(maxlen=12) # recent events: (day, phase, text)
        self.current_action = None  # what the routine said in the last phase
        self.last_phase = None

        self.home = None
        self.workplace = None
        self.shop = None
        self.leisure_spot = None    # TODO set once leisure buildings exist
        self.current_location = None

        self.set_routine(routine)

    def set_routine(self, routine:int=None):
        # no / invalid routine given -> pick a random one
        if routine is None or not 1 <= routine <= len(routines):
            routine = random.randint(1, len(routines))

        self.routine_id = routine
        self.routine = routines[routine]

    def interact_with(self, other:Person):
        pass

    def money(self):
        return self.attributes.money

    @property
    def is_adult(self) -> bool:
        return self.age >= ADULT_AGE

    def can_mate(self) -> bool:
        """alive, in the fertile ages and not already expecting a child"""
        return (self.alive and self.pregnancy is None
                and FERTILE_AGES[0] <= self.age <= FERTILE_AGES[1])

    def become_pregnant(self, due_cycle:int, partner:Person, phase:DayTime=None) -> None:
        self.pregnancy = Pregnancy(due_cycle, partner)
        self.note(phase, f"pregnant with the child of {short_name(partner.name)}, due in cycle {due_cycle}")
        partner.note(phase, f"{short_name(self.name)} is expecting their child, due in cycle {due_cycle}")

    def grow_older(self) -> None:
        """one cycle older"""
        self.age += 1

    def check(self, verbose=False):
        """
        Dies of starvation or old age. Returns whether the person is still alive.
        If both would happen at once, starvation is named as the cause.
        """
        if not self.alive:
            return False

        if self.attributes.hunger >= self.attributes.max_hunger:
            self.die("starvation", verbose=verbose)
        elif self.age >= self.lifespan:
            self.die("old age", verbose=verbose)

        return self.alive

    def die(self, cause:str="unknown", verbose=False):
        self.alive = False
        self.cause_of_death = cause
        self.pregnancy = None
        if verbose: print(f"sim: {self.name} died")

        if self.current_location:
            self.current_location.leave(self)

        if self.workplace:
            self.workplace.dismiss(self)

        if self.home:
            if self in self.home.owners:
                self.home.owners.remove(self)
            self.home = None

    def note(self, phase:DayTime|None, text:str) -> None:
        """remembers something that happened to the person"""
        day = self.ledger.day if self.ledger is not None else 0
        self.log.append((day, phase.name if phase is not None else None, text))

    def _record(self, kind:str, amount:int) -> None:
        if self.ledger is not None:
            self.ledger.record(kind, amount)

    def earn(self, amount:int, phase:DayTime=None, source:str=None) -> None:
        """money earned by working"""
        self.attributes += Stats(money=amount)
        self.totals["money_earned"] += amount
        self._record("wages_paid", amount)
        self.note(phase, f"earned {amount} at {source}" if source else f"earned {amount}")

    def is_working(self, phase:DayTime) -> bool:
        return self.routine[phase] == ActionType.WORK

    def destination_for(self, action:ActionType):
        """
        Where the person has to be for the given action.
        Falls back to home if the person has no such place (yet).
        """
        targets = {
            ActionType.GO_TO_WORK: self.workplace,
            ActionType.WORK: self.workplace,
            ActionType.GO_TO_SHOP: self.shop,
            ActionType.SHOP: self.shop,
            ActionType.GO_TO_LEISURE: self.leisure_spot,
            ActionType.LEISURE: self.leisure_spot,
        }
        # wake up, sleep and go home all happen at home
        return targets.get(action) or self.home

    def action(self, phase:DayTime):
        """
        Does what the personal routine says for this phase of the day
        and returns the ActionType. Movement phases are instant for now.
        """
        action = self.routine[phase]
        self.current_action = action
        self.last_phase = phase
        self.go(self.destination_for(action))

        if action == ActionType.SHOP:
            self.buy_food(phase)
        elif action in MEAL_ACTIONS:
            self.eat(phase)

        return action

    def buy_food(self, phase:DayTime=None) -> int:
        """
        Fills up the food inventory (as far as the money allows).
        Only works while the person is in his shop. Returns the amount bought.
        """
        if self.shop is None or self.current_location is not self.shop:
            return 0

        wanted = FOOD_STOCK_TARGET - self.inventory["food"]
        bought = self.shop.sell_food(self, wanted)

        if bought:
            cost = bought * self.shop.food_price
            self.totals["food_bought"] += bought
            self.totals["money_spent"] += cost
            self._record("food_bought", bought)
            self._record("money_spent", cost)
            self.note(phase, f"bought {bought} food for {cost}")

        return bought

    def eat(self, phase:DayTime=None) -> int:
        """
        Eats at home until not hungry anymore or out of food.
        Returns the amount of food eaten.
        """
        if self.home is None or self.current_location is not self.home:
            return 0

        eaten = 0
        while self.attributes.hunger > 0 and self.inventory["food"] > 0:
            self.inventory["food"] -= 1
            self.attributes += Stats(hunger=-FOOD_RELIEF)
            eaten += 1

        if eaten:
            self.totals["food_eaten"] += eaten
            self._record("food_eaten", eaten)
            self.note(phase, f"ate {eaten} food")

        return eaten

    def apply_location(self):
        if self.current_location:
            self.attributes += self.current_location.location_stats()

    def find_place_to_live(self, buildings:list) -> bool:
        """
        Claims a free unit in the first building the person can afford.
        Returns True if a home was found, False otherwise.
        """
        for building in buildings:
            if self.money() < building.rent():
                continue

            unit = building.get_free_unit()
            if unit is not None and unit.claim(self):
                self.home = unit
                return True

        return False

    def find_shop(self, shops:list) -> bool:
        """picks the shop to buy food at, returns False if there is none"""
        self.shop = shops[0] if shops else None
        return self.shop is not None

    def go(self, location):
        if location is None:
            return False

        # leave wherever we were before
        if self.current_location is not None and self.current_location is not location:
            self.current_location.leave(self)

        return location.enter(self)

    def __repr__(self):
        status = "alive" if self.alive else "dead"
        return f"{self.name}: {self.home} {status} ({self.attributes}) food:{self.inventory['food']}"


def main():
    person = Person(name="Minimus")
    mega_person = Person(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=(math.inf, math.inf)))

    print(person, person.money())
    print(mega_person, mega_person.money())


if __name__ == "__main__":
    main()
