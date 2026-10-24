import argparse
import random
import sys
from pathlib import Path

from services import TownHall
from person import Person
from person.maxima import Maxima
from stats import Stats
from buildings import MegaBuilding, Mansion, Tile, WorkBuilding, Shop, Brothel
from simulation import Simulation
from persistence import SaveError, load_state, save_state
from gameserver import GameServer
from itemfeed import ItemFeed
import protocol


SAVE_FILE = Path(__file__).resolve().parent / "savegame.pkl"
ITEMS_DIR = Path(__file__).resolve().parent / "items"

# The first sims have all ages from 0 up to this (the shortest lifespan is 90), so the
# town does not grow old and die all at once.
FOUNDER_MAX_AGE = 89

# work places of the brothel (Maxima is its boss and has one of them)
BROTHEL_PLACES = 40


def build_town(default_food:bool=True) -> TownHall:
    """
    creates a fresh town with its citizens and buildings.
    default_food=False: the shop starts empty, sims starve until items are put into the items folder
    """
    town_hall = TownHall("Small Ville")

    maxima = Maxima()

    minimus = Person(name="Minimus", age=30)
    minimus.attributes += Stats(money=100)
    minimus.set_routine(1) # normal workflow, wakes up at home and sleeps at night

    for _ in range(1000):
        town_hall.add_citizen(Person(age=random.randint(0, FOUNDER_MAX_AGE)))

    town_hall.add_citizen(minimus)
    town_hall.add_citizen(maxima)

    # costs are negative money (rent per round), gains are positive
    poverty_building = MegaBuilding("Mega Poverty 1", stories=100, persons_per_unit=10, health=1, stamina=2, hunger=0, money=0)
    mb = MegaBuilding("Mega Block 1", stories=15, persons_per_unit=3, health=2, stamina=3, money=-2)
    mansion = Mansion("Villa Maxima", health=5, stamina=10, hunger=-3)

    town_hall.add_building(poverty_building)
    town_hall.add_building(mb)
    town_hall.add_building(mansion, (5,5))

    town_hall.add_building(Tile("Grass Land", "GL"), (-5,-5))
    town_hall.add_building(Tile("Grass Land", "GL"), (-10,-10))
    town_hall.add_building(Tile("Grass Land", "GL"), (10,10))
    town_hall.add_building(Tile("Grass Land", "GL"), (10,0))

    factory = WorkBuilding("Small Factory", work_places=600)
    shop = Shop("Corner Shop", work_places=300, food_price=5, default_food=default_food)
    brothel = Brothel("Velvet Room", boss=maxima, work_places=BROTHEL_PLACES, price=10)
    town_hall.add_building(factory)
    town_hall.add_building(shop)
    town_hall.add_building(brothel)

    print(town_hall)

    homeless = 0
    for person in town_hall.citizens:
        if not person.find_place_to_live(town_hall.list_of_buildings()):
            homeless += 1
    print(f"homeless: {homeless}")

    for building in town_hall.home_buildings:
        print(repr(building))

    # grown ups get a shop, a place to relax (the brothel) and a job at the workplace that is emptiest
    # (factory, shop or brothel). Children stay at home. Minimus and Maxima get no job (Maxima is the
    # boss of the brothel). Whoever finds no job has no money to buy food.
    for person in town_hall.citizens:
        if person is maxima or person is minimus:
            person.find_shop(town_hall.shop_buildings)
            person.find_leisure_spot(town_hall.leisure_buildings)
        elif person.is_adult:
            town_hall.integrate_adult(person)
    children = sum(1 for person in town_hall.citizens if not person.is_adult)
    print(f"employees: factory {len(factory.employees)}, shop {len(shop.employees)}, "
          f"brothel {len(brothel.employees)} (boss {brothel.boss.name}), children: {children}")

    return town_hall


# While the query server is running the game pauses this long after every phase,
# so the server thread gets its turn to look at the town.
MIN_PHASE_DELAY = 0.001


def run_cycles(sim:Simulation, cycles:int|None, save_path, phase_delay:float=0.0, feed:ItemFeed=None) -> int:
    """
    Runs `cycles` days (None = no limit) and saves the state after every day.
    `phase_delay` is a pause in seconds after every phase (to watch the town).
    `feed` is the items folder: after every day the new files are applied, then the
    state is saved, and only then the applied files are renamed. That order makes sure
    that items are never lost: an interrupted game either has them in the save, or
    the file is still there to be applied again.
    Stops early when nobody is alive anymore. Returns the number of days run.
    """
    days = 0
    while cycles is None or days < cycles:
        if not sim.living():
            print("Everybody is dead.")
            break

        sim.run_cycle(phase_delay)
        if feed is not None:
            feed.poll(sim)
        save_state(sim, save_path)
        if feed is not None:
            feed.finish()
        days += 1

        totals, report = sim.totals(), sim.last_cycle()
        print(f"cycle {sim.cycle}: alive {totals['alive']}, died {report['died']}, new {report['new']}, "
              f"food {totals['food']}, shop revenue {totals['revenue']}")

    return days


def non_negative_int(text:str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return value


def non_negative_float(text:str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return value


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="TownSim - a small town simulation")
    parser.add_argument("-c", "--cycles", type=non_negative_int, default=None, metavar="N",
                        help="number of cycles (days) to run; runs until stopped (Ctrl+C) if omitted")
    parser.add_argument("--save-file", type=Path, default=SAVE_FILE, metavar="FILE",
                        help=f"where the state is saved after every cycle (default: {SAVE_FILE.name})")
    parser.add_argument("--new", action="store_true",
                        help="start a new town even if a save file exists (overwrites it)")
    parser.add_argument("-d", "--delay", type=non_negative_float, default=0.0, metavar="SECONDS",
                        help="pause after every phase of the day, to watch the town (default: 0)")
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT,
                        help=f"port console.py and display.py connect to (default: {protocol.DEFAULT_PORT})")
    parser.add_argument("--no-server", action="store_true",
                        help="do not let console.py / display.py connect to the game")
    parser.add_argument("--items-dir", type=Path, default=ITEMS_DIR, metavar="DIR",
                        help=f"folder to drop item files into while the game runs (default: {ITEMS_DIR.name}/)")
    parser.add_argument("--no-items", action="store_true", help="do not watch an items folder")
    parser.add_argument("--empty-shops", action="store_true",
                        help="new town only: the shop starts without food, sims starve until you drop items "
                             "into the items folder")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.save_file.exists() and not args.new:
        try:
            sim = load_state(args.save_file)
        except SaveError as error:
            print(f"error: {error}", file=sys.stderr)
            print("use --new to start a new town (this overwrites the save file)", file=sys.stderr)
            return 1
        print(f"resumed {sim.town_hall.town_name} from {args.save_file} at cycle {sim.cycle}")
        if args.empty_shops:
            print("warning: --empty-shops only counts for a new town, use --new as well", file=sys.stderr)
    else:
        sim = Simulation(build_town(default_food=not args.empty_shops))
        save_state(sim, args.save_file)
        print(f"started a new town, saving to {args.save_file}")

    feed = None
    if not args.no_items:
        feed = ItemFeed(args.items_dir)
        try:
            feed.ensure_folder()
            print(f"items: put JSON files into {args.items_dir} while the game runs (see README)")
        except OSError as error:
            print(f"warning: cannot use the items folder {args.items_dir} ({error})", file=sys.stderr)
            feed = None

    server = None
    if not args.no_server:
        try:
            server = GameServer(sim, port=args.port)
            server.start()
            print(f"console.py and display.py can connect on {server.host}:{server.port}")
        except OSError as error:
            print(f"warning: no console server on port {args.port} ({error}). "
                  "Is another game running? Use --port to pick another port.", file=sys.stderr)

    # without the server nobody needs a pause between the phases
    phase_delay = args.delay if server is None else max(args.delay, MIN_PHASE_DELAY)

    try:
        run_cycles(sim, args.cycles, args.save_file, phase_delay, feed)
    except KeyboardInterrupt:
        # the interrupt may have hit in the middle of a cycle, so go back to
        # the last complete state that was saved
        sim = load_state(args.save_file)
        print(f"\nstopped, last saved state: cycle {sim.cycle}")
    finally:
        if server is not None:
            server.stop()

    print(f"cycle {sim.cycle}, alive: {len(sim.living())}, deaths so far: {sim.deaths}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
