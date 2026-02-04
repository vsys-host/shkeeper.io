from shkeeper.modules.classes.optimism import Optimism


class op_usdt(Optimism):
    _display_name = "OPTIMISM ERC20 USDT"

    def __init__(self):
        self.crypto = "OP-USDT"

    def getname(self):
        return "OP-USDT"
