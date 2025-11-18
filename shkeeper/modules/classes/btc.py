from os import environ
import json
from shkeeper import requests
import datetime
from collections import namedtuple
from decimal import Decimal
from flask import current_app as app
from shkeeper.modules.classes.crypto import Crypto


class Btc(Crypto):
    can_set_tx_fee = False
    network_currency = "BTC"

    def gethost(self):
        host = environ.get("BTC_API_SERVER_HOST", "bitcoin-shkeeper")
        port = environ.get("BTC_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get(f"BTC_USERNAME", "shkeeper")
        password = environ.get(f"BTC_PASSWORD", "shkeeper")
        return (username, password)

    def estimate_tx_fee(self, amount, **kwargs):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/calc-tx-fee/{amount}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    @property
    def fee_deposit_account(self):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/fee-deposit-account",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)

        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(response["account"], Decimal(response["balance"]))

    def balance(self):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/balance",
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)
            balance = response["balance"]
        except Exception as e:
            app.logger.warning(f"Error: {e}")
            balance = False

        return Decimal(balance)

    def get_confirmations_by_txid(self, txid):
        transactions = self.getaddrbytx(txid)
        _, _, confirmations, _ = transactions[0]
        return confirmations

    def get_task(self, id):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/task/{id}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def getstatus(self):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/status",
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)
            delta_blocks = response["delta_blocks"]
            if delta_blocks <= 12:
                return "Synced"
            else:
                return f"Sync In Progress ({delta_blocks} blocks behind)"

        except Exception as e:
            return "Offline"

    def mkaddr(self, **kwargs):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/generate-address",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        addr = response["address"]
        return addr

    def getaddrbytx(self, tx):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/transaction/{tx}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        app.logger.warning(f"Transaction {tx} response: {response}")
        result = []
        for address, amount, confirmations, category in response:
            result.append([address, Decimal(amount), confirmations, category])
        return result

    def dump_wallet(self):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/dump",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        # content = json.dumps(response['accounts'], indent=4)
        content = json.dumps(response, indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {"error": None}

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought BTC to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount -= fee
        current_fee = (
            fee
            if fee not in (None, 0, 0.0, "0", "")
            else self.estimate_tx_fee(amount)["fee_satoshi"]
        )
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}/{current_fee}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def multipayout(self, payout_list):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/multipayout",
            auth=self.get_auth_creds(),
            json=payout_list,
        ).json(parse_float=Decimal)
        return response

    def metrics(self):
        host = str(self.gethost())
        host = host.split(":")[0].replace("-", "_")
        try:
            success_text = f"# HELP {host}_status Connection status to {host}\n# TYPE {host}_status gauge\n{host}_status 1.0\n"
            return (
                requests.get(
                    f"http://{self.gethost()}/metrics", auth=self.get_auth_creds()
                ).text
                + success_text
            )
        except Exception as e:
            error_text = f"# HELP {host}_status Connection status to {host}\n# TYPE {host}_status gauge\n{host}_status 0.0\n"
            return error_text

    def get_all_addresses(self):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/get_all_addresses",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response
