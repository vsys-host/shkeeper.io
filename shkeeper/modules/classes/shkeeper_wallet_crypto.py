from abc import abstractmethod
import datetime
import json
from collections import namedtuple
from decimal import Decimal
from os import environ

from flask import current_app as app

from shkeeper import requests
from shkeeper.modules.classes.crypto import Crypto


class UtxoLikeWalletCrypto(Crypto):
    can_set_tx_fee = False
    default_port = "6000"
    sync_block_threshold = 12

    @property
    @abstractmethod
    def env_prefix(self):
        pass

    @property
    @abstractmethod
    def default_host(self):
        pass

    @property
    def network_currency(self):
        return self.env_prefix

    def gethost(self):
        host = environ.get(f"{self.env_prefix}_API_SERVER_HOST", self.default_host)
        port = environ.get(f"{self.env_prefix}_SERVER_PORT", self.default_port)
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get(f"{self.env_prefix}_USERNAME", "shkeeper")
        password = environ.get(f"{self.env_prefix}_PASSWORD", "shkeeper")
        return (username, password)

    def _api_url(self, path):
        return f"http://{self.gethost()}/{self.crypto}/{path}"

    def _api_post(self, path, **kwargs):
        return requests.post(
            self._api_url(path),
            auth=self.get_auth_creds(),
            **kwargs,
        ).json(parse_float=Decimal)

    def estimate_tx_fee(self, amount, **kwargs):
        return self._api_post(f"calc-tx-fee/{amount}")

    @property
    def fee_deposit_account(self):
        response = self._api_post("fee-deposit-account")

        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(response["account"], Decimal(response["balance"]))

    def balance(self):
        try:
            response = self._api_post("balance")
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
        return self._api_post(f"task/{id}")

    def getstatus(self):
        try:
            response = self._api_post("status")
            delta_blocks = response["delta_blocks"]
            if delta_blocks <= self.sync_block_threshold:
                return "Synced"
            return f"Sync In Progress ({delta_blocks} blocks behind)"
        except Exception:
            return "Offline"

    def mkaddr(self, **kwargs):
        response = self._api_post("generate-address")
        return response["address"]

    def getaddrbytx(self, tx):
        response = self._api_post(f"transaction/{tx}")
        app.logger.warning(f"Transaction {tx} response: {response}")
        result = []
        for address, amount, confirmations, category in response:
            result.append([address, Decimal(amount), confirmations, category])
        return result

    def dump_wallet(self):
        response = self._api_post("dump")
        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        content = json.dumps(response, indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {"error": None}

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return (
                    f"Payout failed: not enought {self.network_currency} to pay for "
                    f"transaction. Need {fee}, balance {amount}"
                )
            amount -= fee
        current_fee = (
            fee
            if fee not in (None, 0, 0.0, "0", "")
            else self.estimate_tx_fee(amount)["fee_satoshi"]
        )
        return self._api_post(f"payout/{destination}/{amount}/{current_fee}")

    def multipayout(self, payout_list):
        return self._api_post("multipayout", json=payout_list)

    def metrics(self):
        host = str(self.gethost())
        host = host.split(":")[0].replace("-", "_")
        try:
            success_text = (
                f"# HELP {host}_status Connection status to {host}\n"
                f"# TYPE {host}_status gauge\n"
                f"{host}_status 1.0\n"
            )
            response = requests.get(
                f"http://{self.gethost()}/metrics",
                auth=self.get_auth_creds(),
                timeout=10,
            )
            response.raise_for_status()
            return response.text + success_text
        except Exception:
            error_text = (
                f"# HELP {host}_status Connection status to {host}\n"
                f"# TYPE {host}_status gauge\n"
                f"{host}_status 0.0\n"
            )
            return error_text

    def get_all_addresses(self):
        return self._api_post("get_all_addresses")

