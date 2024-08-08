from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class ltc(BitcoinLikeCrypto):
    def __init__(self):
        self.crypto = "LTC"

    def getname(self):
        return "Litecoin"

    def gethost(self):
        return "litecoind:9332"
