# Small Town Simmulation

## Project Tree
```
TownSim
├── idea.md
├── README.md
├── src
│   ├── buildings
│   │   ├── home_building.py
│   │   ├── __init__.py
│   │   ├── mansion.py
│   │   ├── mega_building.py
│   │   └── unit.py
│   ├── main.py
│   ├── person
│   │   ├── __init__.py
│   │   ├── maxima.py
│   │   └── person.py
│   ├── services
│   │   ├── __init__.py
│   │   └── townhall.py
│   ├── stats.py
│   └── tests
│       ├── test_buildings.py
│       └── test_person.py
└── venv
```

### Person(Sim)
A person is called a Sim, like in the Sims.

### Buildings
Defines the buildings we need

### Services
Contains leisure and work spaces.   
Sims can work at a bar for example and also enjoy it in the free time.

## Rules
Create Model for a small town. The Town contains up to 10_000 People.

People live in homes go to work, have free time and they need to sleep and eat.
People age and eventually die, so they must procreate.

People can work in shifts.

The Simmulation repeats the cycle of: Morning, MorningMovement, LateMorning, LateMorningMovement, Noon, NoonMovement, AfterNoon, AfterNoonMovement, Evening, EveningMovement, Night, NightMovement.

The Town contains buildings of the Type:

    - House (People live and sleep here)
    - Workplace (People work and earn money)
    - Shop (People buy food)
    - Leisure (People relax and meet)
    
People are genderless (so they can mate with anyone).
People live 100 cycles
After two People mates, one of them will randomly become the 'mother' and bring a new person into the Sim after 2 Cycles.

The town has one Townhall. Here all buildings and jobs will be registered.


All Buildings should be modeled in own classes and files.

Person should be a own class.

Persons should remember where they live and work.

A Person has a health-pool which decays by 1 each day. To Restore it, the person needs to eat.

A Person needs to buy food at the shop. 
The Food will be stored in the persons inventory.
The Person can consume the food at home.

A Workplace has workers.
Workers will receive money each day for working: boss: 100m, office: 50m, worker: 25m

Workers know what shift they work on.

The update method of all the buldings should contain the daily busines for all workers that are currently at work.


Write the Code in Python.
