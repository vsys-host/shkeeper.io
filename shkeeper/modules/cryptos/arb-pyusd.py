from shkeeper.modules.classes.arbitrum import Arbitrum


class arb_pyusd(Arbitrum):
    _display_name = "ARBITRUM ERC20 PYUSD"

    def __init__(self):
        self.crypto = "ARB-PYUSD"

    def getname(self):
        return "ARB-PYUSD"
