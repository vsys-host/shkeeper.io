from shkeeper.modules.classes.ethereum import Ethereum


class eth_usdt(Ethereum):
    _display_name = "ERC20 USDT"

    def __init__(self):
        self.crypto = "ETH-USDT"

    def getname(self):
        return "ETH-USDT"
