from buildings import Building
from person import Person


class Tile(Building):

    def __init__(self, name="Empty Tile", short_hand="ET", owner:Person=None):
        Building.__init__(self)
        self.name = name
        self.short_hand = short_hand
        self.owner = owner

    def __str__(self) -> str:
        return self.short_hand
