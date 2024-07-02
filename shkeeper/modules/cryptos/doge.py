from shkeeper.modules.classes.dogecoin import Dogecoin


class doge(Dogecoin):
    wallet_created = True
    def __init__(self):
        self.crypto="DOGE"
    def getname(self):
        return "Dogecoin"
    def gethost(self):
        return "dogecoind:22555"
