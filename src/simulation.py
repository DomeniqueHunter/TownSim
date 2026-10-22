import threading
import time
from collections import Counter

from buildings import Unit
from person import DayTime, ActionType, ADULT_AGE
import reproduction
from stats import Stats


PHASES = list(DayTime)


def location_label(location) -> str:
    """short readable name of a location, used for the census"""
    if location is None:
        return "nowhere"
    if isinstance(location, Unit):
        return "home"
    return getattr(location, "name", None) or str(location)


class Simulation:
    """
    Runs the town through time.

    One cycle is one day. A day consists of all DayTime phases
    (Morning, MorningMovement, Noon, ...). In every phase each living
    citizen does what its routine says. At the end of the day the home
    effects and the daily hunger malus are applied and the dead are removed.

    `lock` is held while a phase runs. Whoever wants to look at the town from
    another thread (the query server) takes it to see a consistent state.
    """

    def __init__(self, town_hall, daily_malus:Stats=None):
        self.town_hall = town_hall
        self.daily_malus = daily_malus or Stats(hunger=1)

        self.cycle = 0          # number of completed days
        self.phase_index = 0    # next phase to run

        # everybody who is in the town now is a founder, only those who
        # arrive later are "new" in the cycle they arrive
        self.town_hall.collect_newcomers()

        self.lock = threading.RLock()

    # a lock cannot be saved, a new one is made when the state is loaded
    def __getstate__(self):
        state = self.__dict__.copy()
        del state["lock"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.lock = threading.RLock()

    @property
    def deaths(self) -> int:
        """how many died since the start (everybody in the graveyard)"""
        return len(self.town_hall.graveyard)

    @property
    def phase(self) -> DayTime:
        """the phase that will run on the next step"""
        return PHASES[self.phase_index]

    def clock(self) -> dict:
        """what time it is: the day and the phase that ran last"""
        if self.phase_index == 0:
            day = max(self.cycle, 1)
            last = PHASES[-1] if self.cycle > 0 else None
        else:
            day = self.cycle + 1
            last = PHASES[self.phase_index - 1]

        return {
            "cycle": self.cycle,
            "day": day,
            "phase": last.name if last else None,
            "next_phase": self.phase.name,
        }

    def living(self) -> list:
        return [citizen for citizen in self.town_hall.citizens if citizen.alive]

    def step(self) -> DayTime:
        """runs one phase of the day, returns the phase that was run"""
        with self.lock:
            phase = self.phase
            self.town_hall.ledger.day = self.cycle + 1

            relaxing = []
            for citizen in self.living():
                if citizen.action(phase) == ActionType.LEISURE:
                    relaxing.append(citizen)

            # daily business of the buildings (e.g. wages for those who work right now)
            for building in self.town_hall.work_buildings:
                building.update(phase)

            # who relaxes in the same place can meet, and mate
            reproduction.meet(self.town_hall, relaxing, self.cycle + 1, phase)

            self.phase_index += 1
            if self.phase_index == len(PHASES):
                self.phase_index = 0
                self.cycle += 1
                self._end_of_day()

            return phase

    def run_cycle(self, phase_delay:float=0.0) -> None:
        """
        Runs until the current day is over. `phase_delay` is a pause (seconds)
        after every phase, it slows the town down and gives other threads a
        chance to look at it between two phases.
        """
        while True:
            self.step()
            if phase_delay > 0:
                time.sleep(phase_delay)
            if self.phase_index == 0:
                break

    def run(self, cycles:int, phase_delay:float=0.0) -> int:
        """runs several days, stops early if everybody is dead. Returns days run."""
        days = 0
        for _ in range(cycles):
            if not self.living():
                break
            self.run_cycle(phase_delay)
            days += 1
        return days

    def _end_of_day(self) -> None:
        came_of_age = []
        for citizen in self.living():
            # the home works on you wherever you spent the day
            if citizen.home:
                citizen.attributes += citizen.home.location_stats()

            # children are fed by the household, only grown ups get hungry
            if citizen.is_adult:
                citizen.attributes += self.daily_malus
            citizen.grow_older()
            if citizen.age == ADULT_AGE:
                came_of_age.append(citizen)

            if not citizen.check():
                self.town_hall.graveyard.bury(citizen.name, self.cycle, citizen.cause_of_death or "unknown")

        # babies that are due are born (their mother must have survived the day)
        reproduction.give_births(self.town_hall, self.cycle)

        # whoever just grew up gets a shop and a job (if one is free)
        for citizen in came_of_age:
            if citizen.alive:
                self.town_hall.integrate_adult(citizen)

        died = self.town_hall.graveyard.died_in(self.cycle)
        newcomers = self.town_hall.collect_newcomers()

        living = self.living()
        self.town_hall.ledger.close_day(
            self.cycle,
            alive=len(living),
            food_stock=sum(citizen.inventory["food"] for citizen in living),
            died=len(died),
            new=len(newcomers),
        )

        self.town_hall.remove_dead_citizens()

    def last_cycle(self) -> dict:
        """what happened in the cycle that ended last: how many died and how many are new"""
        history = self.town_hall.ledger.history
        last = history[-1] if history else {}
        return {"cycle": last.get("day", 0), "died": last.get("died", 0), "new": last.get("new", 0)}

    def totals(self) -> dict:
        """a few numbers about the town"""
        living = self.living()
        return {
            "alive": len(living),
            "deaths": self.deaths,
            "food": sum(citizen.inventory["food"] for citizen in living),
            "revenue": sum(shop.revenue for shop in self.town_hall.shop_buildings),
        }

    def census(self) -> Counter:
        """how many living citizens are where right now"""
        return Counter(location_label(citizen.current_location) for citizen in self.living())
