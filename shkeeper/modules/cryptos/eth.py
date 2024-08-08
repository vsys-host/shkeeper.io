from shkeeper.modules.classes.ethereum import Ethereum


class eth(Ethereum):
    def __init__(self):
        self.crypto = "ETH"

    def getname(self):
        return "Ethereum"
