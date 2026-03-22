import math


class Stats:
    """
    Stats will be added/removed to/from the Attributes
    Attribute modification
    """

    # attribute: value
    attrs = {'health': 0, 'stamina': 0, 'hunger': 0, 'money': 0}

    def __init__(self, attributes:dict=attrs):
        for attr, value in attributes.items():
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

    # attribute: (min, max)
    attrs = {
        'health': (0, 10),
        'stamina': (0, 10),
        'hunger': (0, 10),
        'money': (0, math.inf),
    }

    def __init__(self, **kwargs):
        for attr, (min_val, max_val) in self.attrs.items():
            if attr in kwargs:
                value = kwargs[attr]

                # allow tuple (current, max) or single value
                if isinstance(value, tuple):
                    current, max_override = value
                    self.__dict__[attr] = current
                    self.__dict__[f"max_{attr}"] = max_override
                else:
                    self.__dict__[attr] = value
                    self.__dict__[f"max_{attr}"] = max_val
            else:
                # default: start at max except hunger-style cases
                default_current = min_val if min_val == 0 and max_val != math.inf else max_val
                self.__dict__[attr] = default_current
                self.__dict__[f"max_{attr}"] = max_val

    def __add__(self, other: Stats):
        if isinstance(other, Stats):
            for attr in self.attrs:
                current = self.__dict__[attr]
                max_val = self.__dict__[f"max_{attr}"]
                delta = other.__dict__.get(attr, 0)

                new_value = current + delta

                # clamp
                new_value = max(0, min(new_value, max_val))

                self.__dict__[attr] = new_value

        return self

    def __repr__(self):
        return " ".join(
            f"{attr}:{self.__dict__[attr]}/{self.__dict__[f'max_{attr}']}"
            for attr in self.attrs
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
    st2 = Stats({'health': -20, 'money': 100_000})
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