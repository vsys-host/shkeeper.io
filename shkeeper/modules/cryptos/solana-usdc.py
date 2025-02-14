from shkeeper.modules.classes.solana import Solana


class solana_usdc(Solana):
    _display_name = "SOLANA SPL USDC"

    def __init__(self):
        self.crypto = "SOLANA-USDC"

    def getname(self):
        return "SOLANA-USDC"
