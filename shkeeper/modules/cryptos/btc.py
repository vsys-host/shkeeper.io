from shkeeper.modules.classes.btc import Btc

class btc(Btc):
    def __init__(self):
        self.crypto = "BTC"

    def getname(self):
        return "Bitcoin"
