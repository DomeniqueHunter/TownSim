"""
How new sims come into the world (rules from idea.md):

* Sims are genderless, any two can mate.
* Two sims meet while they relax (LEISURE) in the same place. Until there are
  leisure buildings that is the home they share.
* When they mate, one of them (picked by chance) is the "mother". The baby
  is born two cycles later.
* A baby lives with its mother if there is room in her unit, else in another
  home it can have for free. Mating only works while there is a free place
  for every baby that is on its way.
"""

import random

from person import Person, short_name


# chance that two sims who meet (and can mate) really do
MATE_CHANCE = 0.2
# the baby is born at the end of the cycle that is this many cycles after the mating
PREGNANCY_CYCLES = 2


def pregnant_count(town_hall) -> int:
    return sum(1 for citizen in town_hall.citizens if citizen.alive and citizen.pregnancy is not None)


def meet(town_hall, people_at_leisure:list, cycle:int, phase=None, rng=random) -> int:
    """
    Sims who relax at the same place are paired up at random. Each pair mates
    with MATE_CHANCE. `cycle` is the number of the running cycle.
    Returns the number of new pregnancies.
    """
    groups = {}
    for person in people_at_leisure:
        if person.current_location is not None and person.can_mate():
            groups.setdefault(id(person.current_location), []).append(person)

    pregnancies, room = 0, None
    for group in groups.values():
        if len(group) < 2:
            continue
        rng.shuffle(group)

        for first, second in zip(group[0::2], group[1::2]):
            if rng.random() >= MATE_CHANCE:
                continue

            if room is None:        # only needed when somebody really wants a baby
                room = town_hall.free_home_places() - pregnant_count(town_hall)
            if room <= 0:
                return pregnancies

            mother, other = (first, second) if rng.random() < 0.5 else (second, first)
            mother.become_pregnant(cycle + PREGNANCY_CYCLES, other, phase)
            room -= 1
            pregnancies += 1

    return pregnancies


def give_births(town_hall, cycle:int) -> list:
    """
    Every living mother whose baby is due (at the end of this cycle, or earlier
    if it was missed) gets it. The baby becomes a citizen. Returns the babies.
    """
    babies = []
    for mother in [c for c in town_hall.citizens if c.alive and c.pregnancy is not None]:
        pregnancy = mother.pregnancy
        if pregnancy.due_cycle > cycle:
            continue

        other = pregnancy.partner
        baby = Person(age=0, parents=(str(mother.name), str(other.name)))

        mother.pregnancy = None
        mother.children += 1
        if other.alive:
            other.children += 1

        town_hall.add_citizen(baby)
        town_hall.place_newborn(baby, mother)

        mother.note(None, f"gave birth to {short_name(baby.name)}")
        if other.alive:
            other.note(None, f"{short_name(mother.name)} gave birth to their child {short_name(baby.name)}")
        baby.note(None, f"born to {short_name(mother.name)} and {short_name(other.name)}")

        babies.append(baby)

    return babies
