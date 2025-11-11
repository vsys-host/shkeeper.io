import abc
import inspect
import os
from typing import Dict


class Crypto(abc.ABC):
    instances: Dict[str, "Crypto"] = {}
    wallet_created = False
    has_autopayout = True
    can_set_tx_fee = True
    _display_name = None
    fixed_fee_steps = []
    precision = 8
    fee_description = "sat/Byte"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return

        default_off = [
            # Tron
            "trx",
            "usdt",
            "usdc",
            # Ethereum
            "eth",
            "eth_usdc",
            "eth_usdt",
            "eth_pyusd",
            # Monero
            "Monero",
            # BNB
            "bnb",
            "bnb_usdt",
            "bnb_usdc",
            # XRP
            "xrp",
            # MATIC
            "matic",
            "polygon_usdt",
            "polygon_usdc",
            # AVALANCHE
            "avax",
            "avalanche_usdt",
            "avalanche_usdc",
            # Lightning
            "BitcoinLightning",
            # Solana
            "sol",
            "solana_usdt",
            "solana_usdc",
            "solana_pyusd",

        ]
        default_on = ["btc", "ltc", "doge"]
        for symbol in default_off:
            if cls.__name__ == symbol and (
                f"{symbol.upper()}_WALLET" not in os.environ
                or os.environ[f"{symbol.upper()}_WALLET"] != "enabled"
            ):
                return

        for symbol in default_on:
            if (
                cls.__name__ == symbol
                and f"{symbol.upper()}_WALLET" in os.environ
                and os.environ[f"{symbol.upper()}_WALLET"] == "disabled"
            ):
                return

        instance = cls()
        cls.instances[instance.crypto] = instance

    def only_read_mode(self):
        network_currency = getattr(self, 'network_currency', None)
        if network_currency is None:
            return False

        return os.environ.get(f"{network_currency}_READ_MODE") == 'enabled'

    @abc.abstractmethod
    def getname(self):
        pass

    @abc.abstractmethod
    def gethost(self):
        pass

    @abc.abstractmethod
    def balance(self):
        pass

    @abc.abstractmethod
    def getstatus(self):
        pass

    @abc.abstractmethod
    def mkaddr(self, **kwargs):
        pass

    @abc.abstractmethod
    def getaddrbytx(self, tx):
        pass

    @abc.abstractmethod
    def dump_wallet(self):
        pass

    @abc.abstractmethod
    def create_wallet(self):
        pass

    @abc.abstractmethod
    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        pass

    @abc.abstractmethod
    def get_all_addresses(self):
        pass

    @property
    def wallet(self):
        return self._wallet.query.filter_by(crypto=self.crypto).first()

    @property
    def display_name(self):
        return self._display_name or self.getname()
