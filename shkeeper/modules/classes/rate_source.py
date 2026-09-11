from abc import ABCMeta, abstractmethod
from decimal import Decimal


class RateSource(metaclass=ABCMeta):
    instances = {}

    USDT_CRYPTOS = {"USDT", "ETH-USDT", "ETH-DAI", "BNB-USDT", "POLYGON-USDT", "AVALANCHE-USDT", "ETH-PYUSD", "SOLANA-PYUSD", "SOLANA-USDT", "ARB-PYUSD", "OP-USDT", "TON-USDT"}
    USDC_CRYPTOS = {"ETH-USDC", "BNB-USDC", "POLYGON-USDC", "AVALANCHE-USDC", "SOLANA-USDC", "ARB-USDC", "OP-USDC"}
    BTC_CRYPTOS = {"BTC", "BTC-LIGHTNING"}
    FIRO_CRYPTOS = {"FIRO", "FIRO-SPARK"}
    ETH_CRYPTOS = {"ARBETH", "OPETH"}
  

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        instance = cls()
        cls.instances[instance.name] = instance

    @classmethod
    def usdt_usd_parity_rate(cls, fiat, crypto):
        if fiat == "USD" and crypto in cls.USDT_CRYPTOS:
            return Decimal(1.0)
        return None

    @classmethod
    def normalize_crypto_symbol(cls, crypto, *, map_ton_to_gram=False):
        if crypto in cls.USDC_CRYPTOS:
            crypto = "USDC"

        if crypto in cls.USDT_CRYPTOS:
            crypto = "USDT"

        if crypto in cls.BTC_CRYPTOS:
            crypto = "BTC"

        if crypto in cls.FIRO_CRYPTOS:
            crypto = "FIRO"

        if crypto in cls.ETH_CRYPTOS:
            crypto = "ETH"

        if crypto == "ARB-TOKEN":
            crypto = "ARB"

        if crypto == "OP-TOKEN":
            crypto = "OP"

        # MATIC (native currency in Polygon renamed to POL)
        if crypto == "MATIC":
            crypto = "POL"

        if map_ton_to_gram and crypto == "TON":
            crypto = "GRAM"

        return crypto

    @classmethod
    def normalize_fiat_symbol(cls, fiat):
        if fiat == "USD":
            fiat = "USDT"
        return fiat

    @classmethod
    def normalize_symbols(cls, fiat, crypto, *, usdt_usd_parity=True, usd_to_usdt=True, map_ton_to_gram=False):
        if usdt_usd_parity:
            parity = cls.usdt_usd_parity_rate(fiat, crypto)
            if parity is not None:
                return parity, fiat, crypto

        crypto = cls.normalize_crypto_symbol(crypto, map_ton_to_gram=map_ton_to_gram)

        if usd_to_usdt:
            fiat = cls.normalize_fiat_symbol(fiat)

        return None, fiat, crypto

    @abstractmethod
    def get_rate(self, fiat, crypto):
        pass
