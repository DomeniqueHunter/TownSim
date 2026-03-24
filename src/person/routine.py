from enum import Enum, auto
from typing import Dict, List


class DayTime(Enum):
    MORNING = auto()
    MORNING_MOVEMENT = auto()
    NOON = auto()
    NOON_MOVEMENT = auto()
    AFTERNOON = auto()
    AFTERNOON_MOVEMENT = auto()
    EVENING = auto()
    EVENING_MOVEMENT = auto()
    NIGHT = auto()
    NIGHT_MOVEMENT = auto()


class ActionType(Enum):
    WAKEUP = auto()
    GO_TO_WORK = auto()
    WORK = auto()
    GO_TO_SHOP = auto()
    SHOP = auto()
    GO_TO_LEISURE = auto()
    LEISURE = auto()
    GO_HOME = auto()
    SLEEP = auto()


# shoult be generated but stays until generator is tested enough
__test_routines: Dict[int, Dict[DayTime, ActionType]] = {
    1: {
        DayTime.MORNING: ActionType.WAKEUP,
        DayTime.MORNING_MOVEMENT: ActionType.GO_TO_WORK,
        DayTime.NOON: ActionType.WORK,
        DayTime.NOON_MOVEMENT: ActionType.GO_TO_SHOP,
        DayTime.AFTERNOON: ActionType.SHOP,
        DayTime.AFTERNOON_MOVEMENT: ActionType.GO_TO_LEISURE,
        DayTime.EVENING: ActionType.LEISURE,
        DayTime.EVENING_MOVEMENT: ActionType.GO_HOME,
        DayTime.NIGHT: ActionType.SLEEP,
        DayTime.NIGHT_MOVEMENT: ActionType.SLEEP,
    },

    2: {
        DayTime.MORNING: ActionType.SLEEP,
        DayTime.MORNING_MOVEMENT: ActionType.SLEEP,
        DayTime.NOON: ActionType.WAKEUP,
        DayTime.NOON_MOVEMENT: ActionType.GO_TO_WORK,
        DayTime.AFTERNOON: ActionType.WORK,
        DayTime.AFTERNOON_MOVEMENT: ActionType.GO_TO_SHOP,
        DayTime.EVENING: ActionType.SHOP,
        DayTime.EVENING_MOVEMENT: ActionType.GO_TO_LEISURE,
        DayTime.NIGHT: ActionType.LEISURE,
        DayTime.NIGHT_MOVEMENT: ActionType.GO_HOME,
    },

    3: {
        DayTime.MORNING: ActionType.LEISURE,
        DayTime.MORNING_MOVEMENT: ActionType.GO_HOME,
        DayTime.NOON: ActionType.SLEEP,
        DayTime.NOON_MOVEMENT: ActionType.SLEEP,
        DayTime.AFTERNOON: ActionType.WAKEUP,
        DayTime.AFTERNOON_MOVEMENT: ActionType.GO_TO_WORK,
        DayTime.EVENING: ActionType.WORK,
        DayTime.EVENING_MOVEMENT: ActionType.GO_TO_SHOP,
        DayTime.NIGHT: ActionType.SHOP,
        DayTime.NIGHT_MOVEMENT: ActionType.GO_TO_LEISURE,
    },

    4: {
        DayTime.MORNING: ActionType.SHOP,
        DayTime.MORNING_MOVEMENT: ActionType.GO_TO_LEISURE,
        DayTime.NOON: ActionType.LEISURE,
        DayTime.NOON_MOVEMENT: ActionType.GO_HOME,
        DayTime.AFTERNOON: ActionType.SLEEP,
        DayTime.AFTERNOON_MOVEMENT: ActionType.SLEEP,
        DayTime.EVENING: ActionType.WAKEUP,
        DayTime.EVENING_MOVEMENT: ActionType.GO_TO_WORK,
        DayTime.NIGHT: ActionType.WORK,
        DayTime.NIGHT_MOVEMENT: ActionType.GO_TO_SHOP,
    },

    5: {
        DayTime.MORNING: ActionType.WORK,
        DayTime.MORNING_MOVEMENT: ActionType.GO_TO_SHOP,
        DayTime.NOON: ActionType.SHOP,
        DayTime.NOON_MOVEMENT: ActionType.GO_TO_LEISURE,
        DayTime.AFTERNOON: ActionType.LEISURE,
        DayTime.AFTERNOON_MOVEMENT: ActionType.GO_HOME,
        DayTime.EVENING: ActionType.SLEEP,
        DayTime.EVENING_MOVEMENT: ActionType.SLEEP,
        DayTime.NIGHT: ActionType.WAKEUP,
        DayTime.NIGHT_MOVEMENT: ActionType.GO_TO_WORK,
    },
}


def routine_generator() -> Dict[int, Dict[DayTime, ActionType]]:
    base: Dict[DayTime, ActionType] = {
        DayTime.MORNING: ActionType.WAKEUP,
        DayTime.MORNING_MOVEMENT: ActionType.GO_TO_WORK,
        DayTime.NOON: ActionType.WORK,
        DayTime.NOON_MOVEMENT: ActionType.GO_TO_SHOP,
        DayTime.AFTERNOON: ActionType.SHOP,
        DayTime.AFTERNOON_MOVEMENT: ActionType.GO_TO_LEISURE,
        DayTime.EVENING: ActionType.LEISURE,
        DayTime.EVENING_MOVEMENT: ActionType.GO_HOME,
        DayTime.NIGHT: ActionType.SLEEP,
        DayTime.NIGHT_MOVEMENT: ActionType.SLEEP,
    }

    times: List[DayTime] = list(DayTime)
    actions: List[ActionType] = [base[t] for t in times]

    routines: Dict[int, Dict[DayTime, ActionType]] = {}

    for i in range(5):
        shift = 2 * i

        if shift == 0:
            rotated = actions[:]
        else:
            rotated = actions[-shift:] + actions[:-shift]

        routine: Dict[DayTime, ActionType] = {}

        for idx, time in enumerate(times):
            routine[time] = rotated[idx]

        routines[i + 1] = routine

    return routines


routines = routine_generator()


def test() -> None:
    for k, v in routines.items():
        print(k, v)
        print(v == __test_routines[k])


if __name__ == "__main__":
    test()
