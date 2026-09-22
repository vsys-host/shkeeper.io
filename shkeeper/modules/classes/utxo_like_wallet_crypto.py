from abc import abstractmethod
import datetime
import json
from collections import namedtuple
from decimal import Decimal

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
        from os import environ

        host = environ.get(f"{self.env_prefix}_API_SERVER_HOST", self.default_host)
        port = environ.get(f"{self.env_prefix}_SERVER_PORT", self.default_port)
        return f"{host}:{port}"

    def get_auth_creds(self):
        from os import environ

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

    def _store_payload(self, store_id=None):
        return {"store_id": int(store_id) if store_id is not None else 1}

    def _crypto_store_ids(self, store_id=None):
        if store_id is not None:
            return [int(store_id)]
        from shkeeper.models import StoreWallet

        store_ids = {1}
        store_ids.update(
            sw.store_id
            for sw in StoreWallet.query.filter_by(crypto=self.crypto).all()
            if sw.store_id
        )
        return sorted(store_ids)

    def estimate_tx_fee(self, amount, **kwargs):
        payload = self._store_payload(store_id=kwargs.get("store_id"))
        dest = kwargs.get("destination") or kwargs.get("dest") or kwargs.get("address")
        if dest:
            payload["dest"] = dest
        return self._api_post(
            f"calc-tx-fee/{amount}",
            json=payload,
        )

    @property
    def fee_deposit_account(self):
        # UTXO has no FDA; return store balance + first address for UI compatibility.
        return self.fee_deposit_account_for()

    def fee_deposit_account_for(self, store_id=None):
        response = self._api_post(
            "fee-deposit-account",
            json=self._store_payload(store_id=store_id),
        )
        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(
            response.get("account") or "",
            Decimal(response.get("balance") or 0),
        )

    def create_fee_deposit_account(self, store_id=None):
        # UTXO has no FDA. Kept for API compatibility; store provisioning
        # marks UTXO wallets READY without generating an address.
        return self.mkaddr(store_id=store_id)

    def balance(self, store_id=None):
        return self.balance_for_account(store_id=store_id)

    def balance_for_account(self, store_id=None):
        try:
            response = self._api_post(
                "balance",
                json=self._store_payload(store_id=store_id),
            )
            balance = response["balance"]
        except Exception as e:
            app.logger.warning(f"Error: {e}")
            balance = False

        return Decimal(balance)

    def get_confirmations_by_txid(self, txid, store_id=None):
        transactions = self.getaddrbytx(txid, store_id=store_id)
        real = [
            row
            for row in transactions
            if len(row) > 3 and row[3] in ("send", "receive")
        ]
        rows = real or transactions
        if not rows:
            raise RuntimeError(f"No transaction details for {txid}")
        return max(int(row[2] or 0) for row in rows)

    def get_task(self, id, store_id=None):
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
        store_id = kwargs.get("store_id")
        response = self._api_post(
            "generate-address",
            json=self._store_payload(store_id=store_id),
        )
        if response.get("status") == "error" or "address" not in response:
            msg = response.get("msg") or response.get("message") or str(response)
            if "password" in msg.lower() or "shkeeper" in msg.lower():
                raise RuntimeError(
                    "Wallet encryption is locked. Ask the admin to unlock it at /unlock "
                    "or via POST /api/v1/decryption-key before creating payment addresses."
                )
            raise RuntimeError(f"Failed to generate address: {msg}")
        return response["address"]

    def getaddrbytx(self, tx, store_id=None):
        merged = []
        for sid in self._crypto_store_ids(store_id):
            try:
                response = self._api_post(
                    f"transaction/{tx}",
                    json=self._store_payload(store_id=sid),
                )
            except Exception:
                app.logger.exception(
                    "Failed to load tx %s for store_id=%s", tx, sid
                )
                continue
            app.logger.warning(
                f"Transaction {tx} store_id={sid} response: {response}"
            )
            if isinstance(response, dict) and response.get("status") == "error":
                app.logger.warning(
                    "Skipping tx %s for store_id=%s: %s", tx, sid, response
                )
                continue
            if not isinstance(response, list):
                app.logger.warning(
                    "Skipping non-list tx %s for store_id=%s: %s", tx, sid, response
                )
                continue
            merged.extend(response)
        result = []
        for row in merged:
            if not isinstance(row, (list, tuple)) or len(row) < 4:
                continue
            address, amount, confirmations, category = row[:4]
            if amount is None:
                amount = 0
            try:
                amount = Decimal(str(amount))
            except Exception:
                continue
            result.append([address, amount, confirmations, category])
        return result

    def dump_wallet(self, store_id=None):
        # Sidecar dump is always store-scoped. When store_id is omitted (admin
        # backup), merge dumps for default store + every known StoreWallet.
        if store_id is None:
            from shkeeper.models import StoreWallet

            store_ids = {1}
            store_ids.update(
                sw.store_id
                for sw in StoreWallet.query.filter_by(crypto=self.crypto).all()
                if sw.store_id
            )
            merged = {}
            errors = []
            for sid in sorted(store_ids):
                part = self._api_post(
                    "dump",
                    json=self._store_payload(store_id=sid),
                    timeout=60,
                )
                if not isinstance(part, dict) or part.get("status") == "error":
                    errors.append(f"store_id={sid}: {part}")
                    continue
                merged.update(part)
            if errors:
                raise RuntimeError(
                    f"Wallet dump failed for {self.crypto}: " + "; ".join(errors)
                )
            response = merged
        else:
            response = self._api_post(
                "dump",
                json=self._store_payload(store_id=store_id),
                timeout=60,
            )
        if isinstance(response, dict) and response.get("status") == "error":
            raise RuntimeError(f"Wallet dump failed for {self.crypto}: {response}")
        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        content = json.dumps(response, indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {"error": None}

    def _payout_fee_coin(self, estimate, amount):
        amount = Decimal(amount)
        sats_per_coin = Decimal("100000000")
        fee_coin = Decimal(str(estimate.get("fee") or 0)) / sats_per_coin
        if fee_coin < amount:
            return fee_coin
        fee_rate = Decimal(str(estimate.get("fee_satoshi") or 0))
        if fee_rate > 0:
            size_based = fee_rate * Decimal("226") / sats_per_coin
            if size_based < amount:
                return size_based
        return fee_coin

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False, store_id=None):
        fee_estimate = None
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee_estimate = self.estimate_tx_fee(
                amount, store_id=store_id, destination=destination
            )
            fee_coin = self._payout_fee_coin(fee_estimate, amount)
            if fee_coin >= amount:
                return (
                    f"Payout failed: not enough {self.network_currency} to pay for "
                    f"transaction. Need {fee_coin} fee, balance {amount}"
                )
            amount -= fee_coin
        current_fee = (
            fee
            if fee not in (None, 0, 0.0, "0", "")
            else (fee_estimate or self.estimate_tx_fee(amount, store_id=store_id))["fee_satoshi"]
        )
        payload = {"store_id": int(store_id) if store_id is not None else 1}
        return self._api_post(
            f"payout/{destination}/{amount}/{current_fee}",
            json=payload,
        )

    def multipayout(self, payout_list, store_id=None):
        serializable_payouts = []
        for item in payout_list:
            entry = dict(item)
            if "amount" in entry and isinstance(entry["amount"], Decimal):
                entry["amount"] = str(entry["amount"])
            serializable_payouts.append(entry)
        payload = {
            "payouts": serializable_payouts,
            "store_id": int(store_id) if store_id is not None else 1,
        }
        return self._api_post("multipayout", json=payload)

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

    def get_all_addresses(self, store_id=None):
        return self._api_post(
            "get_all_addresses",
            json=self._store_payload(store_id=store_id),
        )
