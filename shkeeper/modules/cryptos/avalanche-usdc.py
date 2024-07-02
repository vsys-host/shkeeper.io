from shkeeper.modules.classes.avalanche import Avalanche


class avalanche_usdc(Avalanche):

    _display_name = "AVALANCHE ERC20 USDC"

    def __init__(self):
        self.crypto="AVALANCHE-USDC"

    def getname(self):
        return "AVALANCHE-USDC"