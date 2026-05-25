from shkeeper.modules.classes.ton import Ton


class ton_usdt(Ton):
    _display_name = "Jetton USDT"

    def __init__(self):
        self.crypto = "TON-USDT"

    def getname(self):
        return "TON-USDT"
