from abc import abstractmethod
from decimal import Decimal
from os import environ
import datetime
import json
from collections import namedtuple

from shkeeper import requests
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto


class TronToken(Crypto):
    can_set_tx_fee = False
    network_currency = "TRX"
    account_activation_fee = (
        1.1  # https://developers.tron.network/docs/account#account-activation
    )

    def gethost(self):
        host = environ.get("TRON_API_SERVER_HOST", "localhost")
        port = environ.get("TRON_API_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get(f"{self.crypto}_USERNAME", "shkeeper")
        password = environ.get(f"{self.crypto}_PASSWORD", "shkeeper")
        return (username, password)

    def balance(self):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/balance",
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)
            balance = response["balance"]
        except Exception as e:
            app.logger.exception("balance error")
            balance = False

        return Decimal(balance)

    def getstatus(self):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/status",
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)

            block_ts = response["last_block_timestamp"]
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 3
            if delta < block_interval * 10:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception as e:
            return "Offline"

    def mkaddr(self, **kwargs):
        data = {'xpub': self.wallet.xpub}
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/generate-address",
            auth=self.get_auth_creds(),
            json=data
        ).json(parse_float=Decimal)
        addr = response["base58check_address"]
        return addr

    def getaddrbytx(self, txid):
        txs = requests.post(
            f"http://{self.gethost()}/{self.crypto}/transaction/{txid}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return [
            [
                tx["address"],
                Decimal(tx["amount"]),
                tx["confirmations"],
                tx["category"],
            ]
            for tx in txs
        ]

    def get_confirmations_by_txid(self, txid):
        transactions = self.getaddrbytx(txid)
        _, _, confirmations, _ = transactions[0]
        return confirmations

    def dump_wallet(self):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/dump",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)

        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        content = json.dumps(response["accounts"], indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {"error": None}

    @property
    def fee_deposit_account(self):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/fee-deposit-account",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)

        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(response["account"], Decimal(response["balance"]))

    def estimate_tx_fee(self, amount, **kwargs):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/calc-tx-fee/{amount}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought TRX to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount -= fee
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def get_task(self, id):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/task/{id}",
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

    def servers_status(self):
        response = requests.get(
            f"http://{self.gethost()}/{self.crypto}/multiserver/status",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response["statuses"]

    def multiserver_set_server(self, server_id):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/multiserver/change/{server_id}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def metrics(self):
        return requests.get(
            f"http://{self.gethost()}/metrics", auth=self.get_auth_creds()
        ).text

    def get_all_addresses(self):
        response = requests.get(
            f"http://{self.gethost()}/{self.crypto}/addresses",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response["accounts"]
