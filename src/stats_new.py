import math
import copy


class Stats:
    """
    Stats will be added/removed to/from the Attributes
    Attribute modification
    """

    # attribute: value
    stats_schema = {'health': 0, 'stamina': 0, 'hunger': 0, 'money': 0}

    def __init__(self, attributes:dict=None, **kwargs):
        _attributes = copy.deepcopy(self.stats_schema)

        if attributes is not None:
            _attributes.update(attributes)
        elif kwargs:
            _attributes.update(kwargs)

        for attr, value in _attributes.items():
            self.__dict__[attr] = value

    def __int__(self):
        return sum([i for i in self.__dict__.values()])

    def __add__(self, other):
        if isinstance(other, Stats):
            for key in self.__dict__:
                if key in other.__dict__:
                    self.__dict__[key] += other.__dict__[key]
        return self

    def __str__(self):
        return ", ".join(f"{key}: {value}" for key, value in self.__dict__.items())


class Attributes:
    """
    Attributes are the stats of a character

    init describes the start,max values of the char
    """

    # attribute: (current_val, max_val)
    attributes_schema = {
        'health': (0, 10),
        'stamina': (0, 10),
        'hunger': (0, 10),
        'money': (0, math.inf),
    }

    def __init__(self, attributes:dict=None, **kwargs):
        _attributes = copy.deepcopy(self.attributes_schema)

        if attributes is not None:
            _attributes.update(attributes)
        elif kwargs:
            _attributes.update(kwargs)

        for attr, (current_val, max_val) in _attributes.items():
            self.__dict__[attr] = current_val
            self.__dict__[f"max_{attr}"] = max_val

    def __add__(self, other: Stats):
        if isinstance(other, Stats):
            for attr in Stats.stats_schema:
                # skip if attribute does not exist in other
                if not hasattr(other, attr):
                    continue

                current_value = getattr(self, attr)
                other_value = getattr(other, attr)
                max_value = getattr(self, f"max_{attr}")

                new_value = current_value + other_value

                if new_value > max_value:
                    new_value = max_value
                elif new_value < 0:
                    new_value = 0

                setattr(self, attr, new_value)

        return self

    def __repr__(self):
        return " ".join(
            f"{attr}:{self.__dict__[attr]}/{self.__dict__[f'max_{attr}']}"
            for attr in self.attributes_schema
        )


def test():
    stats = Stats({'health': 5, 'stamina': 3, 'hunger': 4, 'money': 2})
    stats2 = Stats({'health': 2, 'stamina': 3, 'hunger': 4, 'money': 10})
    
    print(stats)
    print(stats.__dict__)
    print(int(stats))
    print(stats + stats2)

    attr = Attributes(health=(10, 100))
    attrs = {
        'health': (0, 100),
        'stamina': (0, 10),
        'hunger': (0, 10),
        'money': (0, math.inf),
    }
    st = Stats({'health': 100, 'money': 100_000_000})
    st2 = Stats({'health':-20, 'money': 100_000})
    
    print(attr)
    print('stats:', st + st2)

    attr + st
    print(attr)
    print('#########################################\n\n')
    attr + st2
    print(attr)
    print('#########################################\n\n')
    attr + st2
    print(attr)


if __name__ == "__main__":
    test()
