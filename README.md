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

- Sims are **male, female or futa** (see Genders below). To mate a sim has to be **18 to 50** (`FERTILE_AGES`) and not
  already expecting a child, and the two need to be a pair that can have a baby together.
- Two sims **meet while they relax (LEISURE) in the same place**: in the brothel, which is the leisure place of
  every grown up, or at home with the ones they share a unit with if they have no leisure place or are not let
  in. Sims who relax together are paired up at random, and every pair wants a baby with a chance of 20%
  (`MATE_CHANCE`). **All couples of a day compete at the end of the cycle**, in random order, for the free
  places (so it does not matter at which time of the day somebody relaxes).
- The one who can carry the baby is the "mother" (a coin flip if both could). The baby is born **2 cycles later** (`PREGNANCY_CYCLES`),
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
| `stock` | yes | whole number >= 0, how much is delivered, counted in `unit`s (pieces if there is no `unit`/`portion`) |
| `effects` | for food | what one piece does when eaten: `hunger`, `health`, `stamina`, whole numbers. A food has to lower hunger (`hunger` negative) |
| `description` | no | free text |
| `store` | no | name of the shop that gets the pieces, default: the first shop |
| `deliver_to` | no | name of a sim: the pieces go straight into his inventory, not into a shop. `stock` must be at least 1 whole piece. Cannot be combined with `store` |
| `unit` | no | what `stock` is counted in, for example `l` or `kg`, 1 to 20 characters. Default `piece` |
| `portion` | no | whole number >= 1, how many `unit`s make one **piece**, which is what a sim buys, holds and eats. Default 1 |

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

**A town needs a place where everybody meets.** Without one, sims only meet the ones they live with, and a baby needs a
male and a female (or a futa) of fertile age who relax in the same unit in the same phase, which almost never
happens: in tests such towns had 2 to 8 times fewer births and most died out within 250 cycles. With the brothel
as the meeting place the demo town holds its population (about 980) for hundreds of cycles. So the town depends on
its brothel being open: without a living boss nobody is let in, and without a meeting place the births stop.


## The brothel

`Brothel` (`buildings/brothel.py`) is a workplace and the first leisure place of the town. The demo town has one,
the "Velvet Room", with **Maxima as its boss**.

- **Needs a boss.** `Brothel("Name", boss=somebody)` fails without one. The boss works there (boss wage 100) and
  the brothel is **open only while it has a living boss**. If the boss dies, nobody is let in and nobody is paid
  until `club.appoint_boss(somebody)` names a new one.
- **Grown ups only.** Only sims of 18 and older can work there (`employ` refuses children), are let in, or can be the boss.
  A sim has one job: somebody who already works elsewhere cannot be employed here as well.
- **Work.** New grown ups are hired at the workplace that is **emptiest** (fewest of its places taken, `TownHall.integrate_adult`),
  and a closed brothel is skipped. So the brothel is staffed like the factory and the shop (about 85 percent of its 40 places
  in the demo town for hundreds of cycles), and a place that became free is filled again soon. Normal wage of a worker.
- **Enjoying.** Every grown up gets the brothel as his leisure place (`TownHall.integrate_adult`). In the
  LEISURE phase he goes there if he can pay the entrance (`price`, default 10, the staff and the boss pay nothing),
  otherwise he stays home. A visit gives `effects` (default `stamina +2`). The money is booked as `leisure_spent`
  (`console.py goods`) and is the revenue of the building. Children never go there.
- **Meeting.** It is where grown ups meet while they relax, see Reproduction above.
- `console.py building "Velvet Room"` shows boss, open or closed, entrance, visits and revenue.

Maxima can have children at **every age from 18 on**: `Person(fertile_ages=(youngest, oldest))`, for Maxima
`(18, infinity)`, for everybody else `FERTILE_AGES = (18, 50)`. The youngest age can never be below 18, for nobody:
`Person` refuses such a range and `can_mate` always asks for a grown up. With the fair decision at the end of the
cycle Maxima had 19 and 25 children in 400 cycles of the demo town (two runs).

Old save files do not fit anymore (the save format changed), start once with `--new`.


## Genders

Every sim is `male`, `female` or `futa` (`Person.gender`, chosen by chance when the sim is made: a futa with a
chance of 1 in 1,000,000, otherwise male or female with the same chance; a baby is made like any other sim, a futa
is not passed on). **Maxima is the futa of the town**, whatever the chance.

- Females and futas can **carry** a baby, males and futas can **father** one.
- So a pair can have a baby if one of them can carry and the other can father: male + female, futa + male,
  futa + female, futa + futa. Two males or two females cannot.
- The **mother** is the one who carries: the female in a male + female pair, the futa when the partner is male,
  the female when the partner is a futa (the futa is the other parent then), a coin flip for two futas.
- Sims who relax in the same place are paired up so that as many pairs as possible can have a baby: males with
  females first, then futas with whoever is left over, then futas with each other.
- `Person.become_pregnant` refuses a male, and a partner who cannot father, so the rule cannot be bypassed.
- `console.py npc <name>` shows the gender, `console.py people` has a gender column, `console.py world` counts them.

`idea.md` still says "People are genderless", this section replaces that rule.

Old save files do not fit anymore (the save format changed), start once with `--new`.


### Bulk deliveries: tankers of milk, sold in bottles

You do not have to make a file for every bottle. A delivery is counted in **units** (`unit`, for example litres) and
the shop splits it into **pieces** of `portion` units. `price` and `effects` are per piece. A tanker of milk:

```json
{
  "format": 1,
  "items": [
    {
      "id": "milk",
      "name": "Milk bottle",
      "category": "food",
      "price": 2,
      "unit": "l",
      "portion": 1,
      "stock": 1000000,
      "effects": { "hunger": -2, "health": 1 },
      "description": "Delivered in tankers of 1,000,000 litres, sold in bottles of 1 litre."
    }
  ]
}
```

(`src/items/_example_milk.json`.) The shop holds **one number** (1,000,000 litres), not a million bottles, and sells
whole pieces out of it. A sim holds bottles in his inventory. For half litre bottles count in millilitres:
`"unit": "ml", "portion": 500, "stock": 1000000000`.

- A delivery that does not make whole pieces keeps the rest: 10 litres in pieces of 3 are 3 pieces and 1 litre waits
  for the next delivery (`console.py items` shows `1 l` or `250 ml` in the column `piece`, `console.py building <shop>`
  shows `milk 2 (1000000 left, 1 l each)`).
- A second delivery of the same item is added to what is on the shelf and sets the new price. `unit` and `portion` are
  part of what the item is and cannot change (like `category` and `effects`).
- A gift (`deliver_to`) has to be whole pieces: `stock` a multiple of `portion`.
- **Nothing is created.** Every unit that is delivered is on the shelf, in the inventory of a sim or eaten
  (there is a test that counts it). What still comes out of thin air: the plain food of the shop (unlimited, start with
  `--empty-shops` to switch it off) and the wages.
- **Supplying the game from another program:** it only has to write the JSON file into the items folder. Write it under a
  name that starts with `_` or `.` (or does not end in `.json`) and rename it to `something.json` when it is complete,
  or just write it directly: the game waits until the file has not changed for a second. Every file that was taken
  over stays in the folder as `_consumed_<name>_<timestamp>.json`, so the folder is also a record of what was delivered.

