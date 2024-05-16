import json
from decimal import Decimal

from shkeeper import requests

from shkeeper.modules.classes.rate_source import RateSource


class Coingate(RateSource):
    name = "coingate"

    def get_rate(self, fiat, crypto):

        if fiat == 'USD' and crypto in {'USDT', 'ETH-USDT', 'BNB-USDT'}:
            return Decimal(1.0)

        if crypto in {'ETH-USDC', 'BNB-USDC'}:
            crypto = 'USDC'

        url = f"https://api.coingate.com/api/v2/rates/merchant/{crypto}/{fiat}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            return Decimal(data)

        raise Exception(f"Can't get rate for {crypto}{fiat}")
