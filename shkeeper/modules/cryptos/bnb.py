from shkeeper.modules.classes.bnb import Bnb


class bnb(Bnb):
    _display_name = "BNB Chain BNB"
    
    def __init__(self):
        self.crypto = "BNB"

    def getname(self):
        return "BNB"
