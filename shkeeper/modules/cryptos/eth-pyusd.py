from shkeeper.modules.classes.ethereum import Ethereum


class eth_pyusd(Ethereum):
    _display_name = "ERC20 PYUSD"

    def __init__(self):
        self.crypto = "ETH-PYUSD"

    def getname(self):
        return "ETH-PYUSD"
