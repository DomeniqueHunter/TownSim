from enum import Enum


class TimePhase(Enum):
    MORNING = 0
    LATE_MORNING = 1
    NOON = 2
    AFTERNOON = 3
    EVENING = 4
    NIGHT = 5


class Activity(Enum):
    SLEEP = "sleep"
    WORK = "work"
    LEISURE = "leisure"
    HOME = "home"


ALL_PHASES = list(TimePhase)

# 3 shifts — at any phase, ~1/3 of people do each activity
SHIFT_SCHEDULES = {
    1: [Activity.WORK, Activity.WORK, Activity.LEISURE, Activity.HOME, Activity.SLEEP, Activity.SLEEP],
    2: [Activity.SLEEP, Activity.SLEEP, Activity.WORK, Activity.WORK, Activity.HOME, Activity.LEISURE],
    3: [Activity.HOME, Activity.LEISURE, Activity.SLEEP, Activity.SLEEP, Activity.WORK, Activity.WORK],
}

NUM_SHIFTS = len(SHIFT_SCHEDULES)


class Schedule:

    def __init__(self, shift: int=1):
        self.shift = shift

    def activity_at(self, phase: TimePhase) -> Activity:
        return SHIFT_SCHEDULES[self.shift][phase.value]

    def destination(self, phase: TimePhase, person):
        activity = self.activity_at(phase)
        if activity in (Activity.SLEEP, Activity.HOME):
            return person.home
        if activity == Activity.WORK:
            return person.workplace or person.home
        if activity == Activity.LEISURE:
            return person.leisure_spot or person.home
        return person.home

    def __repr__(self):
        return f"Schedule(shift={self.shift})"


def test_shift_activities() -> None:
    print("\n=== Testing Shift Activity Mapping ===")

    for shift_id, activities in SHIFT_SCHEDULES.items():
        print(f"\n--- Shift {shift_id} ---")

        schedule = Schedule(shift=shift_id)

        for phase in TimePhase:
            activity = schedule.activity_at(phase)

            expected = activities[phase.value]

            assert activity == expected, (
                f"Mismatch in shift {shift_id} at {phase.name}: "
                f"expected {expected}, got {activity}"
            )

            print(f"{phase.name:<15} -> {activity.value}")


def test_schedule_length() -> None:
    print("\n=== Testing Schedule Lengths ===")

    expected_length = len(TimePhase)

    for shift_id, activities in SHIFT_SCHEDULES.items():
        assert len(activities) == expected_length, (
            f"Shift {shift_id} has incorrect length"
        )
        print(f"Shift {shift_id} OK")


def main() -> None:
    test_schedule_length()
    test_shift_activities()


if __name__ == "__main__":
    main()
