
from .person import Person, ADULT_AGE
from stats import Attributes, Stats

import math


class Maxima(Person):

    def __init__(self, name:str="Maxima", attributes:Attributes=None):
        attributes = attributes or Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000))
        attributes += Stats(money=math.inf)  # cuz she is rich

        # routine 1: normal workflow, wakes up at home and sleeps at night
        # she never dies of old age and can have children at any age. The youngest age stays
        # ADULT_AGE: nobody below that can mate, she is no exception.
        # And she is the futa of the town (everybody else is one in a million).
        super().__init__(name=name, attributes=attributes, routine=1, lifespan=math.inf,
                         fertile_ages=(ADULT_AGE, math.inf), gender="futa")


maxima = Maxima()


def test():
    print(maxima)


if __name__ == "__main__":
    test()
