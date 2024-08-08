from shkeeper.modules.classes.polygon import Polygon


class polygon_usdc(Polygon):
    _display_name = "POLYGON ERC20 USDC"

    def __init__(self):
        self.crypto = "POLYGON-USDC"

    def getname(self):
        return "POLYGON-USDC"
