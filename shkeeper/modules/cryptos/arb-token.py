from shkeeper.modules.classes.arbitrum import Arbitrum


class arb_token(Arbitrum):
    _display_name = "ARBITRUM ERC20 TOKEN"

    def __init__(self):
        self.crypto = "ARB-TOKEN"

    def getname(self):
        return "ARB-TOKEN"
