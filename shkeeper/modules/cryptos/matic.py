from shkeeper.modules.classes.polygon import Polygon


class matic(Polygon):
    _display_name = "POL (prev. MATIC)"

    def __init__(self):
        self.crypto = "MATIC"

    def getname(self):
        return "MATIC"
