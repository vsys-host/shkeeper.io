
from shkeeper.modules.classes.tron_token import TronToken


class usdc(TronToken):
    _display_name = "TRC20 USDC"

    def __init__(self):
        self.crypto = "USDC"

    def getname(self):
        return "USDC"
