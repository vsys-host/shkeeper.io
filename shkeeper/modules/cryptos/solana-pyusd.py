from shkeeper.modules.classes.solana import Solana


class solana_pyusd(Solana):
    _display_name = "SOLANA SPL PYUSD"

    def __init__(self):
        self.crypto = "SOLANA-PYUSD"

    def getname(self):
        return "SOLANA-PYUSD"
