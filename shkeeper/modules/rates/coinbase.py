import json
from decimal import Decimal

from shkeeper import requests
from shkeeper.modules.classes.rate_source import RateSource


class Coinbase(RateSource):
    name = "coinbase"

    def get_rate(self, fiat, crypto):
        parity, fiat, crypto = self.normalize_symbols(fiat, crypto)
        if parity is not None:
            return parity

        url = f"https://api.coinbase.com/v2/exchange-rates?currency={crypto}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            return Decimal(data["data"]["rates"][fiat])

        raise Exception(f"Can't get rate for {crypto} / {fiat}")
