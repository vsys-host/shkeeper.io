import json
from decimal import Decimal

from shkeeper import requests

from shkeeper.modules.classes.rate_source import RateSource


class Binance(RateSource):
    name = "binance"

    def get_rate(self, fiat, crypto):

        if fiat == 'USD' and crypto in {'USDT', 'ETH-USDT', 'BNB-USDT', 'POLYGON-USDT'}:
            return Decimal(1.0)

        if crypto in {'ETH-USDC', 'BNB-USDC', 'POLYGON-USDC'}:
            crypto = 'USDC'

        if fiat == 'USD':
            fiat = 'USDT'
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={crypto}{fiat}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            return Decimal(data['price'])

        raise Exception(f"Can't get rate for {crypto}{fiat}")
