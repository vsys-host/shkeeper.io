from shkeeper.modules.classes.arbitrum import Arbitrum


class arb_usdc(Arbitrum):
    _display_name = "ARBITRUM ERC20 USDC"

    def __init__(self):
        self.crypto = "ARB-USDC"

    def getname(self):
        return "ARB-USDC"
