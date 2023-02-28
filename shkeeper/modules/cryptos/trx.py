import os

from shkeeper.modules.classes.tron_token import TronToken

class trx(TronToken):
    def __init__(self):
        self.crypto="TRX"

    def getname(self):
        return "Tron"
