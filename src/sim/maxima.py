
from sim import Sim
from stats import Attributes

import math

maxima = Sim(name="Maxima", attributes=Attributes(health=(1000, 1000), stamina=(1000, 1000), hunger=(0, 10_000), money=math.inf))
