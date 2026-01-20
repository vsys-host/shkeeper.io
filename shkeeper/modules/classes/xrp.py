from os import environ
from shkeeper import requests
import datetime
from decimal import Decimal
from shkeeper.modules.classes.ethereum import Ethereum


class Xrp(Ethereum):
    network_currency = "XRP"

    def gethost(self):
        host = environ.get("XRP_API_SERVER_HOST", "xrp-shkeeper")
        port = environ.get("XRP_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get("XRP_USERNAME", "shkeeper")
        password = environ.get("XRP_PASSWORD", "shkeeper")
        return (username, password)

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought XRP to pay for transaction. Need {fee}, balance {amount}"
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

            block_ts = (
                int(response["last_block_timestamp"]) + 946684800
            )  # close_time in ledger comes from 01.01.2000 00:00
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 4
            if delta < block_interval * 10:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception:
            return "Offline"
