from shkeeper.modules.classes.polygon import Polygon


class polygon_usdt(Polygon):
    _display_name = "POLYGON ERC20 USDT"

    def __init__(self):
        self.crypto = "POLYGON-USDT"

    def getname(self):
        return "POLYGON-USDT"
