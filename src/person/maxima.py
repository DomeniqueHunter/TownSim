
from person import Person
from stats import Attributes

import math

# maxima = Person(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))

class Maxima(Person):
    
    def __init__(self, name:str="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf)):
        Person.__init__(self)
        self.name = name
        self.attributes = attributes
        
maxima = Maxima()