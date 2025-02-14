from shkeeper.modules.classes.solana import Solana


class sol(Solana):
    def __init__(self):
        self.crypto = "SOL"

    def getname(self):
        return "Solana"
