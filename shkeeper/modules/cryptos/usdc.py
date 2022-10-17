import os

from shkeeper.modules.classes.tron_token import TronToken

class usdc(TronToken):
    def __init__(self):
        self.crypto="USDC"

    def getname(self):
        return "USDC"
