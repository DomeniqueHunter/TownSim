
from person import Person
from stats import Attributes, Stats

import math

# maxima = Person(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))

class Maxima(Person):
    
    def __init__(self, name:str="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000))):
        Person.__init__(self)
        self.name = name
        self.attributes = attributes + Stats(money=math.inf) # cuz she is rich
        
maxima = Maxima()


def test():
    print(maxima)
    
if __name__ == "__main__":
    test()