import os

from shkeeper.modules.classes.tron_token import TronToken

class usdt(TronToken):
    def __init__(self):
        self.crypto="USDT"

    def getname(self):
        return "USDT"

