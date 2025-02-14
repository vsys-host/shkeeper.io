from shkeeper.modules.classes.solana import Solana


class solana_usdt(Solana):
    _display_name = "SOLANA SPL USDT"

    def __init__(self):
        self.crypto = "SOLANA-USDT"

    def getname(self):
        return "SOLANA-USDT"
