# TownSim
Simmulating a small town


## Running

```
cd src
python main.py                 # new town (or resume the saved one), runs until Ctrl+C
python main.py -c 50           # run 50 cycles (days), then stop
python main.py --cycles=50     # same
python main.py --new -c 10     # ignore the save file and start a new town
python main.py --save-file my_town.pkl
```

The state is saved to `src/savegame.pkl` after every cycle. The next start
resumes from it automatically; `--new` starts over (and overwrites it).
If the simulation is stopped in the middle of a cycle, it continues from the
last completed cycle. Save files may become unusable when the classes change.

Tests: `cd src && python -m unittest discover -s tests`

## Economy (current rules)

- Working: whoever is at his workplace during his WORK phase earns the daily wage
  (boss 100, office 50, worker 25). Wages are created out of thin air for now.
- Shopping: during the SHOP phase a person at his shop fills his food inventory up to
  3 items, as far as his money allows (`Shop.food_price`, default 5, unlimited stock).
- Eating: at WAKEUP and GO_HOME, at home, a person eats until hunger is 0 or the food
  is gone (1 food = 1 hunger). Hunger rises by 1 per day, at `max_hunger` the person dies.
  Without money (no job) nobody can buy food and starves after 10 days.


## Looking into the running game

While `main.py` runs it answers questions on `127.0.0.1:7777` (only this computer, read-only,
nothing can be changed through it). Two programs use that:

```
python main.py --delay 0.5          # slow motion: pause 0.5 s after every phase of the day
python main.py --port 7800          # other port (also pass --port to console.py / display.py)
python main.py --no-server          # nobody can look in

python console.py world                   # the town in numbers
python console.py where Maxima            # where is she, what does she do (also: location Maxima)
python console.py npc Maxima              # all her stats, food, money, recent events (also: stats Maxima)
python console.py follow Maxima           # live: a line whenever she goes somewhere or does something
python console.py building "Corner Shop"  # a building, by name or address: building 5,5
python console.py buildings               # all buildings, who is there, how full
python console.py people 20 age           # 20 citizens, sorted by hunger | money | name | age
python console.py graveyard               # the dead: cycle of death, name, cause (also: graveyard 50 | all)
python console.py goods 10                # food bought / eaten, money spent, wages, per day
python console.py map Maxima              # text map of the town, * marks where she is
python console.py                         # interactive mode (type help)

python display.py                         # window: map, goods chart, buildings, one npc (Maxima)
python display.py --watch Minimus         # watch somebody else (or type a name into the window)
```

Names can be shortened to their first letters as long as they are unique (`where max`).
The window needs tkinter (included with Python on Windows/macOS; Debian/Ubuntu: `sudo apt install python3-tk`).

How it fits together: `queries.py` reads the game and answers questions, `gameserver.py` carries them
over a socket (one JSON per line, see `protocol.py`), `client.py` asks, `console.py` and `display.py`
show the answers. `ledger.py` counts food bought/eaten, money spent and wages (today, total and the
last 100 days); every npc also keeps its own lifetime numbers and its last 12 events.


## Graveyard and the cycle log

Everybody who dies is buried in the town's graveyard (`graveyard.py`) with name, cycle of death and
cause, in the order of death. Nobody is removed from it. `console.py graveyard` shows the newest 20
(`graveyard 50`, `graveyard all`), `console.py world` shows the last deaths and what happened in the last cycle.

The log line of `main.py` shows what happened in that cycle only, not totals:

```
cycle 10: alive 902, died 100, new 0, food 2382, shop revenue 52500
cycle 11: alive 902, died 0, new 0, food 2382, shop revenue 57010
```

`new` counts citizens who joined the town during that cycle (births, once they exist). Everybody who is
there when the simulation starts is a founder and not counted. Old save files do not fit anymore
(the save format changed), start once with `--new`.


## Ageing

Every sim has an `age` in cycles (starts at 0, +1 at the end of every cycle) and a `lifespan`, a random
whole number from 90 to 110 picked when the sim is created (`LIFESPAN_RANGE` in `person/person.py`).
When the age reaches the lifespan the sim dies of "old age" and is buried in the graveyard. If a sim
would starve and die of old age in the same cycle, "starvation" is named. Maxima has an infinite
lifespan. `console.py npc <name>` shows `age: 12/97 cycles`, `console.py people 10 age` lists the oldest.

A sim made without an age is grown up (18), babies are made with `age=0`.


## Reproduction

Rules (from `idea.md`, the numbers can be changed in `person/person.py` and `reproduction.py`):

- Sims are genderless, any two can mate. They have to be **18 to 50** (`FERTILE_AGES`) and not already expecting a child.
- Two sims **meet while they relax (LEISURE) in the same place**. Until there are leisure buildings that is the
  home they share, so somebody who lives alone (Maxima in her Villa) never has children. Sims who relax
  together are paired up at random, every pair mates with a chance of 20% (`MATE_CHANCE`).
- One of the two is picked by chance as the "mother". The baby is born **2 cycles later** (`PREGNANCY_CYCLES`),
  at the end of the cycle. If the mother dies before that, the baby is lost.
- Mating only works while there is a free place to live (rent 0) for every baby on its way. The baby lives
  with its mother if her unit has room, else in another free home.
- The baby is a normal sim: age 0, a random lifespan of 90 to 110 cycles, a random routine, a random name.
  It counts as `new` in the log line of the cycle it is born in.

Children and grown ups:

- Under 18 a sim is a child: it stays at home all day, has no job and no shop, and **does not get hungry**
  (the household feeds it, this is a simplification, children cost nothing).
- At 18 the sim gets a shop and the first free job (factory first, then the shop). **This happens once.**
  If no job is free the sim has no income and starves after 10 days. Nobody is hired later, so the number
  of jobs limits the population together with the number of homes.

The demo town (`main.py`) starts with 1000 sims of all ages from 0 to 89, so it does not grow old all at once.
In a 400 cycle test it first drops to about 650 sims (the oldest die while the first babies grow up) and then
holds at about 950 to 990 with 8 to 12 births and deaths per cycle. The limit is the number of homes.
`console.py npc <name>` shows age, parents, number of children and a pregnancy, `console.py world` the number
of children and pregnancies.

Old save files do not fit anymore (the save format changed), start once with `--new`.


## Items: put things into the running game

While the game runs, drop a JSON file into the folder `src/items/` (made at the start, other place: `--items-dir DIR`,
off: `--no-items`). The game takes it over, and renames it to `_consumed_<name>_<timestamp>.json`
(timestamp = seconds since 1970 when it was taken over; a second file in the same second gets `_2`, ...).
Start with `src/items/_example_bread.json`: copy it to `bread.json`. Files that start with `_` or `.` and files
that do not end in `.json` are ignored.

```json
{
  "format": 1,
  "items": [
    {
      "id": "bread",
      "name": "Bread",
      "category": "food",
      "price": 3,
      "stock": 200,
      "effects": { "hunger": -2 },
      "description": "Fresh from the bakery."
    }
  ]
}
```

| field | required | rule |
|---|---|---|
| `format` (top level) | yes | `1` |
| `items` (top level) | yes | list with at least one item |
| `id` | yes | lowercase letters, digits, `_` `-`, starts with a letter, at most 40 characters. Key of the item everywhere |
| `name` | yes | the shown name, 1 to 60 characters |
| `category` | yes | `food` (more categories will come) |
| `price` | yes | whole number >= 0, money per piece |
| `stock` | yes | whole number >= 0, pieces added |
| `effects` | for food | what one piece does when eaten: `hunger`, `health`, `stamina`, whole numbers. A food has to lower hunger (`hunger` negative) |
| `description` | no | free text |
| `store` | no | name of the shop that gets the pieces, default: the first shop |
| `deliver_to` | no | name of a sim: the pieces go straight into his inventory, not into a shop. `stock` must be at least 1. Cannot be combined with `store` |

Rules:

- **Strict.** Only whole numbers (`3`, not `3.5` or `"3"`), no unknown fields (a typo like `pirce` is an error, with a
  hint), no unknown categories, no key twice in one object. Every problem is printed with its place, for example
  `items[0].price: must be a whole number >= 0, got "3"`.
- **All or nothing.** If anything in a file is wrong, also if a shop or sim does not exist, nothing is taken over. An
  invalid file stays where it is and is only looked at again after you changed it.
- **Existing items.** The same `id` again adds the `stock` and replaces the `price`. Category and `effects` must stay the
  same everywhere in the town (a file cannot quietly turn bread into something else), `name` and `description` are
  updated. The plain food of the game has the id `food` (effects `hunger -1`, unlimited stock):
  a file with `"id": "food", "stock": 0` and a new price changes its price.
- **Timing.** A file is read when it has been unchanged for a second (so a file that is still being copied is not judged).
  The game looks between two cycles: items are applied, the state is saved, then the file is renamed.
  An interrupted game never loses items.
- **Optional on purpose:** `store` and `deliver_to`. Without them an item behaves like any other. `deliver_to` is the way
  to make sure something lands at Maxima.

What the sims do with items:

- At the shop a sim fills up to 3 pieces of food (of any kind) as far as his money allows. He takes the **best value
  first** (most hunger relief per money, then the bigger relief), and the next one if that is sold out or too expensive.
- At home (waking up, coming home) he eats until not hungry: the food with the biggest relief that is not wasted first.
  Each piece also does its other `effects` (health, stamina). Pieces that do not lower hunger are never eaten.
- `python main.py --new --empty-shops`: the shop starts without the plain food, so sims starve after 10 days until
  you drop the first items. Without that flag the plain food is always there.
- `console.py items` lists every item with effects, where it is sold and how many pieces sims hold, `console.py building
  "Corner Shop"` shows the shelf, `console.py npc <name>` the inventory.

