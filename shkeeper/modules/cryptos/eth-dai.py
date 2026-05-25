from shkeeper.modules.classes.ethereum import Ethereum


class eth_dai(Ethereum):
    _display_name = "ERC20 DAI"

    def __init__(self):
        self.crypto = "ETH-DAI"

    def getname(self):
        return "ETH-DAI"
