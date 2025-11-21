from abc import ABCMeta, abstractmethod


class RateSource(metaclass=ABCMeta):
    instances = {}

    USDT_CRYPTOS = {"USDT", "ETH-USDT", "BNB-USDT", "POLYGON-USDT", "AVALANCHE-USDT", "ETH-PYUSD", "SOLANA-PYUSD", "SOLANA-USDT"}
    USDC_CRYPTOS = {"ETH-USDC", "BNB-USDC", "POLYGON-USDC", "AVALANCHE-USDC", "SOLANA-USDC"}
    BTC_CRYPTOS = {"BTC", "BTC-LIGHTNING"}
    FIRO_CRYPTOS = {"FIRO", "FIRO-SPARK"}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        instance = cls()
        cls.instances[instance.name] = instance

    @abstractmethod
    def get_rate(self, fiat, crypto):
        pass
