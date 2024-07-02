from shkeeper.modules.classes.litecoin import Litecoin


class ltc(Litecoin):
    def __init__(self):
        self.crypto="LTC"
    def getname(self):
        return "Litecoin"
    def gethost(self):
        return "litecoind:9332"
