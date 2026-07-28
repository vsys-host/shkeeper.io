from abc import abstractmethod
from os import environ
import json
from shkeeper import requests
import datetime
from collections import namedtuple
from decimal import Decimal
from flask import current_app as app
from shkeeper.modules.classes.crypto import Crypto


class Ethereum(Crypto):
    can_set_tx_fee = False
    network_currency = "ETH"

    def gethost(self):
        host = environ.get("ETHEREUM_API_SERVER_HOST", "ethereum-shkeeper")
        port = environ.get("ETHEREUM_SERVER_PORT", "6000")
        return f"{host}:{port}"

    def get_auth_creds(self):
        username = environ.get(f"ETH_USERNAME", "shkeeper")
        password = environ.get(f"ETH_PASSWORD", "shkeeper")
        return (username, password)

    def estimate_tx_fee(self, amount, **kwargs):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/calc-tx-fee/{amount}",
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def _fda_payload(self, account=None, fda_key=None, sweep_target=None):
        payload = {}
        if account:
            payload["from_account"] = account
        if fda_key:
            payload["fda_key"] = fda_key
        if sweep_target:
            payload["sweep_target"] = sweep_target
        return payload or None

    @property
    def fee_deposit_account(self):
        return self.fee_deposit_account_for()

    def fee_deposit_account_for(self, account=None, fda_key=None):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/fee-deposit-account",
            auth=self.get_auth_creds(),
            json=self._fda_payload(account=account, fda_key=fda_key),
        ).json(parse_float=Decimal)

        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(response["account"], Decimal(response["balance"]))

    def create_fee_deposit_account(self, fda_key=None):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/create-fee-deposit-account",
                auth=self.get_auth_creds(),
                json={"fda_key": fda_key} if fda_key else {},
                timeout=60,
            ).json(parse_float=Decimal)
        except Exception as exc:
            raise Exception(
                f"create-fee-deposit-account failed for {self.crypto}: {exc}"
            ) from exc
        if response.get("status") == "error":
            raise Exception(
                response.get("msg")
                or response.get("message")
                or f"Failed to create fee-deposit account for {self.crypto}"
            )
        account = response.get("account")
        if not account:
            raise Exception(
                f"create-fee-deposit-account bad response for {self.crypto}: {response}"
            )
        return account

    def balance(self, account=None, fda_key=None):
        return self.balance_for_account(account=account, fda_key=fda_key)

    def balance_for_account(self, account=None, fda_key=None):
        try:
            response = requests.post(
                f"http://{self.gethost()}/{self.crypto}/balance",
                auth=self.get_auth_creds(),
                json=self._fda_payload(account=account, fda_key=fda_key),
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

            block_ts = response["last_block_timestamp"]
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 12
            if delta < block_interval * 10:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception as e:
            return "Offline"

    def mkaddr(self, **kwargs):
        fee_deposit_account = kwargs.get("fee_deposit_account")
        fda_key = kwargs.get("fda_key")
        if not fee_deposit_account:
            fda = self.fee_deposit_account_for(fda_key=fda_key)
            fee_deposit_account = fda.addr
        payload = {"fee_deposit_account": fee_deposit_account}
        if fda_key:
            payload["fda_key"] = fda_key
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/generate-address",
            auth=self.get_auth_creds(),
            json=payload,
        ).json(parse_float=Decimal)
        if response.get("status") == "error" or "address" not in response:
            msg = response.get("msg") or response.get("message") or str(response)
            if "password" in msg.lower() or "shkeeper" in msg.lower():
                raise RuntimeError(
                    "Wallet encryption is locked. Ask the admin to unlock it at /unlock "
                    "or via POST /api/v1/decryption-key before creating payment addresses."
                )
            raise RuntimeError(f"Failed to generate address: {msg}")
        return response["address"]

    def getaddrbytx(self, tx):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/transaction/{tx}",
            auth=self.get_auth_creds(),
            timeout=60,
        ).json(parse_float=Decimal)
        result = []
        for address, amount, confirmations, category in response:
            result.append([address, Decimal(amount), confirmations, category])
        return result

    def dump_wallet(self, fda_key=None, sweep_target=None):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/dump",
            auth=self.get_auth_creds(),
            json=self._fda_payload(fda_key=fda_key, sweep_target=sweep_target),
            timeout=60,
        ).json(parse_float=Decimal)
        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        # content = json.dumps(response['accounts'], indent=4)
        content = json.dumps(response, indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {"error": None}

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False, fda_key=None):
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)["fee"])
            if fee >= amount:
                return f"Payout failed: not enought ETH to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount -= fee
        payload = {}
        if fda_key:
            payload["fda_key"] = fda_key
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}",
            auth=self.get_auth_creds(),
            json=payload or None,
        ).json(parse_float=Decimal)
        return response

    def multipayout(self, payout_list, from_account=None, fda_key=None):
        serializable_payouts = []
        for item in payout_list:
            entry = dict(item)
            if "amount" in entry and isinstance(entry["amount"], Decimal):
                entry["amount"] = str(entry["amount"])
            serializable_payouts.append(entry)
        payload = {"payouts": serializable_payouts}
        if from_account:
            payload["from_account"] = from_account
        if fda_key:
            payload["fda_key"] = fda_key
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/multipayout",
            auth=self.get_auth_creds(),
            json=payload,
        ).json(parse_float=Decimal)
        return response

    def metrics(self):
        host = str(self.gethost())
        host = host.split(":")[0].replace("-", "_")
        try:
            success_text = f"# HELP {host}_status Connection status to {host}\n# TYPE {host}_status gauge\n{host}_status 1.0\n"
            response = requests.get(
                f"http://{self.gethost()}/metrics",
                auth=self.get_auth_creds(),
                timeout=10,
            )
            response.raise_for_status()
            return response.text + success_text
        except Exception as e:
            error_text = f"# HELP {host}_status Connection status to {host}\n# TYPE {host}_status gauge\n{host}_status 0.0\n"
            return error_text

    def get_all_addresses(self, fda_key=None, sweep_target=None):
        response = requests.post(
            f"http://{self.gethost()}/{self.crypto}/get_all_addresses",
            auth=self.get_auth_creds(),
            json=self._fda_payload(fda_key=fda_key, sweep_target=sweep_target),
        ).json(parse_float=Decimal)
        return response
