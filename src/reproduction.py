"""
How new sims come into the world (rules from idea.md):

* Sims are male, female or (very rarely) futa. Females and futas can carry a baby, males and
  futas can father one, so a futa can have a baby with anybody, males with females only.
* Two sims meet while they relax (LEISURE) in the same place: in the brothel, or at home
  with the ones they share a unit with.
* When they mate, the one who can carry is the "mother" (a coin flip if both could).
  The baby is born two cycles later and is male or female by chance, like everybody else.
* A baby lives with its mother if there is room in her unit, else in another
  home it can have for free. Mating only works while there is a free place
  for every baby that is on its way.
"""

import math
import random

from person import Person, short_name


# chance that two sims who meet (and can mate) really do. Measured on the demo town with no limit by food
# (1002 sims, 250 cycles): 0.06 and less: the town shrinks, 0.08: it stays as it is, 0.09: it grows to about
# 2 to 2.6 times as many, slowly, 0.095: 2.7 to 3.4 times, 0.1: it doubles in 150 cycles and speeds up.
MATE_CHANCE = 0.09
# the baby is born at the end of the cycle that is this many cycles after the mating
PREGNANCY_CYCLES = 2


def pregnant_count(town_hall) -> int:
    return sum(1 for citizen in town_hall.citizens if citizen.alive and citizen.pregnancy is not None)


def pair_roles(first, second, rng=random):
    """
    Who is the mother and who the other parent of a baby of these two, as (mother, other),
    or None if they cannot have one together (two males, two females). The mother is the one
    who can carry while the other can father, a coin flip if both ways work (two futas).
    """
    options = []
    if first.can_carry and second.can_father:
        options.append((first, second))
    if second.can_carry and first.can_father:
        options.append((second, first))
    return rng.choice(options) if options else None


def pair_up(group:list, rng=random) -> list:
    """
    Pairs the sims of one place who can have a baby together, at random: males with females
    first, then futas with whoever is left over, then futas with each other.
    Who finds nobody stays alone. Returns the pairs.
    """
    group = list(group)
    rng.shuffle(group)
    males = [p for p in group if p.gender == "male"]
    females = [p for p in group if p.gender == "female"]
    futas = [p for p in group if p.gender == "futa"]

    pairs = []
    while males and females:
        pairs.append((males.pop(), females.pop()))
    while futas and (males or females):
        pairs.append((futas.pop(), (males or females).pop()))
    while len(futas) >= 2:
        pairs.append((futas.pop(), futas.pop()))
    return pairs


def meet(people_at_leisure:list, phase=None, rng=random) -> list:
    """
    Sims who relax at the same place find a partner they can have a baby with (see pair_up).
    Each pair wants a baby with MATE_CHANCE. Returns those couples as (first, second, phase).
    Nothing happens to them yet: at the end of the cycle all couples of the day compete
    for the free places (see conceive), so it does not matter in which phase of the
    day somebody relaxes.
    """
    groups = {}
    for person in people_at_leisure:
        if person.current_location is not None and person.can_mate():
            groups.setdefault(id(person.current_location), []).append(person)

    couples = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for first, second in pair_up(group, rng):
            if rng.random() < MATE_CHANCE:
                couples.append((first, second, phase))
    return couples


def conceive(town_hall, couples:list, cycle:int, rng=random) -> int:
    """
    The couples of a cycle (in random order, nobody is favoured) get a baby as long as there is
    a free place to live for every baby on its way. Who carries it is decided by the genders
    (see pair_roles). `cycle` is the cycle that just ended. Returns the number of new pregnancies.
    """
    if not couples:
        return 0

    couples = list(couples)
    rng.shuffle(couples)
    # a town that builds houses for its homeless does not need a free place for every baby
    room = town_hall.free_home_places() - pregnant_count(town_hall) if town_hall.babies_need_homes else math.inf

    pregnancies = 0
    for first, second, phase in couples:
        if room <= 0:
            break
        if not (first.can_mate() and second.can_mate()):       # one may have died in the meantime
            continue
        roles = pair_roles(first, second, rng)
        if roles is None:                                       # not possible with these two
            continue

        mother, other = roles
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
