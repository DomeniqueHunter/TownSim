from typing import NamedTuple


class Grave(NamedTuple):
    name: str
    cycle: int      # the cycle in which the npc died
    cause: str


class Graveyard:
    """
    Everybody who died, in the order of their death. Nobody is ever removed.
    """

    def __init__(self):
        self.graves = []

    def bury(self, name:str, cycle:int, cause:str="unknown") -> Grave:
        grave = Grave(str(name), cycle, cause)
        self.graves.append(grave)
        return grave

    def __len__(self) -> int:
        return len(self.graves)

    def __iter__(self):
        return iter(self.graves)

    def died_in(self, cycle:int) -> list:
        """those who died in the given cycle, in the order of their death"""
        result = []
        for grave in reversed(self.graves):     # newest first, stop as soon as we are past the cycle
            if grave.cycle < cycle:
                break
            if grave.cycle == cycle:
                result.append(grave)
        result.reverse()
        return result

    def latest(self, count:int) -> list:
        """the `count` most recent graves, newest first"""
        return self.graves[::-1][:count]

    def find(self, prefix:str):
        """the most recent grave whose name starts with `prefix` (any case), or None"""
        prefix = prefix.strip().lower()
        if not prefix:
            return None
        for grave in reversed(self.graves):
            if grave.name.lower().startswith(prefix):
                return grave
        return None
