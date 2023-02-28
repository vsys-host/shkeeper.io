import abc
import inspect
import os

class Crypto(abc.ABC):

    instances = {}
    wallet_created = False
    has_autopayout = True

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return

        default_off = [
            # Tron
            'trx',
            'usdt',
            'usdc',
            # Ethereum
            'eth',
            'eth_usdc',
            'eth_usdt',
        ]
        default_on = ['btc', 'ltc', 'doge']
        for symbol in default_off:
            if cls.__name__ == symbol and (f'{symbol.upper()}_WALLET' not in os.environ or
                                           os.environ[f'{symbol.upper()}_WALLET'] != 'enabled'):

                return

        for symbol in default_on:
            if (cls.__name__ == symbol
                and f'{symbol.upper()}_WALLET' in os.environ
                and os.environ[f'{symbol.upper()}_WALLET'] == 'disabled'):
                return

        instance = cls()
        cls.instances[instance.crypto] = instance

    @abc.abstractmethod
    def getname(self): pass

    @abc.abstractmethod
    def gethost(self): pass

    @abc.abstractmethod
    def balance(self): pass

    @abc.abstractmethod
    def getstatus(self): pass

    @abc.abstractmethod
    def mkaddr(self): pass

    @abc.abstractmethod
    def getaddrbytx(self, tx): pass

    @abc.abstractmethod
    def dump_wallet(self): pass

    @abc.abstractmethod
    def create_wallet(self): pass

    @abc.abstractmethod
    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False): pass

    @property
    def wallet(self):
        return self._wallet.query.filter_by(crypto=self.crypto).first()
