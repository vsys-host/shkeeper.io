from shkeeper.modules.classes.ethereum import Ethereum


class eth_usdc(Ethereum):
    
    def __init__(self):
        self.crypto="ETH-USDC"


    def getname(self):
        return "ETH-USDC"
