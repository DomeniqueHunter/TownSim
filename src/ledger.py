from collections import Counter, deque


# things the ledger counts
KINDS = ("food_bought", "food_eaten", "money_spent", "wages_paid")


class Ledger:
    """
    Town wide bookkeeping of goods and money.

    `today` counts the day that is running, `total` everything since the start
    and `history` keeps one entry per finished day (only the last HISTORY_DAYS).
    """

    HISTORY_DAYS = 100

    def __init__(self):
        self.day = 1                        # number of the running day
        self.today = Counter()
        self.total = Counter()
        self.history = deque(maxlen=self.HISTORY_DAYS)

    def record(self, kind:str, amount:int=1) -> None:
        if amount:
            self.today[kind] += amount
            self.total[kind] += amount

    def close_day(self, day:int, **snapshot) -> dict:
        """stores the numbers of the finished day (plus extra info like population)"""
        entry = {"day": day}
        entry.update({kind: self.today.get(kind, 0) for kind in KINDS})
        entry.update(snapshot)

        self.history.append(entry)
        self.today = Counter()
        return entry
