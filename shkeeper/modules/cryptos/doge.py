from shkeeper.modules.classes.crypto import Crypto

class doge(Crypto):
    def __init__(self):
        self.crypto="DOGE"
    def getname(self):
        return "Dogecoin"
    def gethost(self):
        return "dogecoind:22555"