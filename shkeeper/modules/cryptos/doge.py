from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class doge(BitcoinLikeCrypto):
    wallet_created = True

    def __init__(self):
        self.crypto = "DOGE"

    def getname(self):
        return "Dogecoin"

    def gethost(self):
        return "dogecoind:22555"
