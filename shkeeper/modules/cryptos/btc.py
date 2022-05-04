from shkeeper.modules.classes.crypto import Crypto

class btc(Crypto):
    def __init__(self):
        self.crypto="BTC"
    def getname(self):
        return "Bitcoin"
    def gethost(self):
        return "bitcoind:8332"
