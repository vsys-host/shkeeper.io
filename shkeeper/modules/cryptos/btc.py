from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class btc(BitcoinLikeCrypto):
    def __init__(self):
        self.crypto="BTC"
    def getname(self):
        return "Bitcoin"
    def gethost(self):
        return "bitcoind:8332"
