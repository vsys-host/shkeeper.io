from abc import abstractmethod
from os import environ
import json
from shkeeper import requests
import datetime
from collections import namedtuple
from decimal import Decimal
from flask import current_app as app
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.ethereum import Ethereum


class Ton(Ethereum):
    network_currency = "TON"

    def gethost(self):
        host = environ.get("TON_API_SERVER_HOST", "ton-shkeeper")
        port = environ.get("TON_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get(f"TON_USERNAME", "shkeeper")
        password = environ.get(f"TON_PASSWORD", "shkeeper")
        return (username, password)

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought {self.network_currency} to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount = (
                    amount - fee - 10
                )  # 10XRP need to keep the fee-deposit account active
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def getstatus(self):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/status",
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)

            block_ts = int(response["last_block_timestamp"])
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 3
            if delta < block_interval * 10:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception as e:
            return "Offline"
