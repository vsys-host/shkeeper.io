from shkeeper.modules.classes.bnb import Bnb


class bnb_usdt(Bnb):

    _display_name = "BEP20 USDT"

    def __init__(self):
        self.crypto="BNB-USDT"


    def getname(self):
        return "BNB-USDT"