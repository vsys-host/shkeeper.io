from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class btc(BitcoinLikeCrypto):

    fee_description = "sat/vByte"

    def __init__(self):
        self.crypto="BTC"
    def getname(self):
        return "Bitcoin"
    def gethost(self):
        return "10.10.20.130:8332"
