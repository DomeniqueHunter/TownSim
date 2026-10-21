"""a small but complete town for the tests of the console / display / server"""

from buildings import MegaBuilding, Mansion, WorkBuilding, Shop, Tile
from person import Person
from person.maxima import Maxima
from services import TownHall
from simulation import Simulation


def make_sim(workers=3, extra_citizens=0):
    """
    Alice, Alma (routine 2) and Bob (routine 3) work at the Job, Dave has no job,
    Maxima (rich) lives in the Villa. Everybody shops at the Shop.
    `extra_citizens` adds more nameless workers (to make a phase take longer).
    """
    town = TownHall("Testville")
    job = WorkBuilding("Job", work_places=workers + extra_citizens)
    shop = Shop("Shop", work_places=2, food_price=5)

    town.add_building(MegaBuilding("Home Block", stories=extra_citizens + 10, persons_per_unit=1,
                                   health=1, stamina=2, hunger=0, money=0))
    town.add_building(job)
    town.add_building(shop)
    town.add_building(Mansion("Villa", health=5, stamina=10, hunger=-3), (5, 5))
    town.add_building(Tile("Grass Land", "GL"), (3, 3))
    town.add_building(Tile("Grass Land", "GL"), (-3, -3))

    people = [Person(name="Alice", routine=1), Person(name="Alma", routine=2), Person(name="Bob", routine=3)]
    people = people[:workers]
    for person in people:
        job.employ(person)
    people += [Person(name="Dave", routine=1), Maxima()]
    for _ in range(extra_citizens):
        person = Person()
        job.employ(person)
        people.append(person)

    for person in people:
        town.add_citizen(person)
        person.find_place_to_live(town.list_of_buildings())
        person.find_shop(town.shop_buildings)

    return Simulation(town)
