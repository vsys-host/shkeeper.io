from shkeeper.modules.classes.avalanche import Avalanche


class avax(Avalanche):
    _display_name = "Avalanche AVAX"
    
    def __init__(self):
        self.crypto = "AVAX"

    def getname(self):
        return "AVAX"
