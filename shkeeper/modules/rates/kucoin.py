import json
from decimal import Decimal

from shkeeper import requests

from shkeeper.modules.classes.rate_source import RateSource


class KuCoin(RateSource):
    name = "kucoin"

    def get_rate(self, fiat, crypto):
        if crypto in self.USDT_CRYPTOS:
            crypto = "USDT"

        if crypto in self.USDC_CRYPTOS:
            crypto = "USDC"

        if crypto in self.BTC_CRYPTOS:
            crypto = "BTC"

        if crypto in self.FIRO_CRYPTOS:
            crypto = "FIRO"

        # https://www.kucoin.com/docs/beginners/introduction
        url = f"https://api.kucoin.com/api/v1/prices?base={fiat}&currencies={crypto}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            if data.get("code") == "200000":
                # data will be empty dict if symbol doesnt exist even though code is 200000
                price = data.get("data", {}).get(crypto)
                if price is not None:
                    return Decimal(price)

        raise Exception(f"Can't get rate for {crypto} in {fiat}")
