from abc import ABCMeta, abstractmethod


class RateSource(metaclass=ABCMeta):
    instances = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        instance = cls()
        cls.instances[instance.name] = instance

    @abstractmethod
    def get_rate(self, fiat, crypto): pass
