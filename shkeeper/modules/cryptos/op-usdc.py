from shkeeper.modules.classes.optimism import Optimism


class op_usdc(Optimism):
    _display_name = "OPTIMISM ERC20 USDC"

    def __init__(self):
        self.crypto = "OP-USDC"

    def getname(self):
        return "OP-USDC"
