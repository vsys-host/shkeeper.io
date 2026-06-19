from shkeeper.modules.classes.ton import Ton


class ton(Ton):
    _display_name = "GRAM (prev. TON)"

    def __init__(self):
        self.crypto = "TON"

    def getname(self):
        return "TON"
