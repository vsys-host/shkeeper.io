import json
from decimal import Decimal

from shkeeper import requests
from shkeeper.modules.classes.rate_source import RateSource


class Kraken(RateSource):
    name = "kraken"

    def get_rate(self, fiat, crypto):
        if fiat == "USD" and crypto in self.USDT_CRYPTOS:
            return Decimal(1.0)

        if crypto in self.USDC_CRYPTOS:
            crypto = "USDC"

        if crypto in self.BTC_CRYPTOS:
            crypto = "BTC"

        if crypto in self.FIRO_CRYPTOS:
            crypto = "FIRO"

        if fiat == "USD":
            fiat = "USDT"
        url = f"https://api.kraken.com/0/public/Ticker?pair={crypto}{fiat}"
        answer = requests.get(url)
        if answer.status_code == requests.codes.ok:
            data = json.loads(answer.text)
            if len(data["error"]) == 0:
                key = list(data["result"].keys())[0]
                # Last trade closed https://docs.kraken.com/api/docs/rest-api/get-ticker-information
                return Decimal(data["result"][key]["c"][0])

        raise Exception(f"Can't get rate for {crypto} / {fiat}")
