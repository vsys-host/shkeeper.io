from os import environ
from shkeeper import requests
import datetime
from decimal import Decimal
from shkeeper.modules.classes.ethereum import Ethereum


class Solana(Ethereum):
    network_currency = "SOL"

    def gethost(self):
        host = environ.get("SOLANA_API_SERVER_HOST", "solana-shkeeper")
        port = environ.get("SOLANA_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get("SOLANA_USERNAME", "shkeeper")
        password = environ.get("SOLANA_PASSWORD", "shkeeper")
        return (username, password)

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought SOL to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount -= fee
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
            block_ts = response["last_block_timestamp"]
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 1
            if delta < block_interval * 100:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception:
            return "Offline"
