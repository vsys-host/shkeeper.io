from shkeeper.modules.classes.ethereum import Ethereum


class eth_usdc(Ethereum):
    _display_name = "ERC20 USDC"

    def __init__(self):
        self.crypto = "ETH-USDC"

    def getname(self):
        return "ETH-USDC"
