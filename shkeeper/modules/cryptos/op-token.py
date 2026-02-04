from shkeeper.modules.classes.optimism import Optimism


class op_token(Optimism):
    _display_name = "OPTIMISM ERC20 TOKEN"

    def __init__(self):
        self.crypto = "OP-TOKEN"

    def getname(self):
        return "OP-TOKEN"
