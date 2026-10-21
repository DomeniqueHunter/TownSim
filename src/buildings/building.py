from stats import Stats


class Building:
    """
    Base class of all buildings.
    Every building is a place people can be at (enter/leave).
    Homes are split into Units which handle this on their own.
    """

    def __init__(self):
        self.address = None
        self.currently_here = []

    def location_stats(self):
        # what being here does to a person each round, buildings can override
        return Stats()

    def enter(self, person):
        if person not in self.currently_here:
            self.currently_here.append(person)
            person.current_location = self
            return True
        return False

    def leave(self, person):
        if person in self.currently_here:
            self.currently_here.remove(person)
            if person.current_location is self:
                person.current_location = None
            return True
        return False
