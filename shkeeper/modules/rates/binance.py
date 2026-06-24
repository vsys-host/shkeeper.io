import json
from decimal import Decimal

from shkeeper import requests

from shkeeper.modules.classes.rate_source import RateSource


class Binance(RateSource):
    name = "binance"

    def get_rate(self, fiat, crypto):
        parity, fiat, crypto = self.normalize_symbols(fiat, crypto, map_ton_to_gram=True)
        if parity is not None:
            return parity

        url = f"https://api.binance.com/api/v3/ticker/price?symbol={crypto}{fiat}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            return Decimal(data["price"])

        raise Exception(f"Can't get rate for {crypto}{fiat}")
