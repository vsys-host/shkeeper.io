from shkeeper.modules.classes.avalanche import Avalanche


class avalanche_usdt(Avalanche):
    _display_name = "AVALANCHE ERC20 USDT"

    def __init__(self):
        self.crypto = "AVALANCHE-USDT"

    def getname(self):
        return "AVALANCHE-USDT"
