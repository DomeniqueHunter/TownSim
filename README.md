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
python console.py people 20 money         # 20 citizens, sorted by hunger | money | name
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
