import math

class Stats:
    """
    Stats will be added/removed to/from the Attributes
    """
    
    attrs = ['health', 'stamina', 'hunger', 'money']
    
    def __init__(self, *args, health:int=0, stamina:int=0, hunger:int=0, money:int=0):
        self.health = health
        self.stamina = stamina
        self.hunger = hunger
        self.money = money


class Attributes:
    """
    Attributes are the stats of a character

    init describes the start,max values of the char
    """

    def __init__(self, *args, health:tuple=None, stamina:tuple=None, hunger:tuple=None, money:int=0):
        self.health, self.max_health = health or (10, 10)
        self.stamina, self.max_stamina = stamina or (10, 10)
        self.hunger, self.max_hunger = hunger or (0, 10)
        self.money, self.max_money = money, math.inf
        
    def __add__(self, other):
        if type(other) == Stats:
            for attr in Stats.attrs:
                self.__dict__[attr] = self.__dict__[attr]+other.__dict__[attr] if self.__dict__[attr]+other.__dict__[attr] < self.__dict__['max_'+attr] else self.__dict__['max_'+attr]
                
        return  self            
            
    def __repr__(self):
        stats_string = ""
        for attr in Stats.attrs:
            stats_string += f"{attr}:{self.__dict__[attr]}/{self.__dict__['max_'+attr]} "
        return stats_string


def test():
    attr = Attributes(health=(10, 100))
    st = Stats(health=100, money=100_000_000)
    st2 = Stats(health=-20, money=100_000)
    print(attr)    
    
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
