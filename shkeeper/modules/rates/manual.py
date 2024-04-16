import json
from decimal import Decimal

from shkeeper import requests

from shkeeper.modules.classes.rate_source import RateSource


class Manual(RateSource):
    name = "manual"

    def get_rate(self, fiat, crypto):
        raise Exception(f"Manual rate provider has no get_rate()")
