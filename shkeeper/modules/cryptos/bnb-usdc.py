from shkeeper.modules.classes.bnb import Bnb


class bnb_usdc(Bnb):
    _display_name = "BEP20 USDC"

    def __init__(self):
        self.crypto = "BNB-USDC"

    def getname(self):
        return "BNB-USDC"
