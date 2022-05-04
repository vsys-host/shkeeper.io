from shkeeper.modules.classes.crypto import Crypto

class ltc(Crypto):
    def __init__(self):
        self.crypto="LTC"
    def getname(self):
        return "Litecoin"
    def gethost(self):
        return "litecoind:9332"