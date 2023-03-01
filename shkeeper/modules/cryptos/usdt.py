import os

from shkeeper.modules.classes.tron_token import TronToken

class usdt(TronToken):

    _display_name = "TRC20 USDT"

    def __init__(self):
        self.crypto="USDT"

    def getname(self):
        return "USDT"
