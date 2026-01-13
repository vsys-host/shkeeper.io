import os
from decimal import Decimal
from typing import List, Literal, Tuple

from flask import current_app as app

from monero import const
from monero.backends.jsonrpc import JSONRPCWallet
from monero.backends.jsonrpc.exceptions import RPCError
from monero.daemon import Daemon
from monero.numbers import from_atomic
from monero.wallet import Wallet

from shkeeper.modules.classes.crypto import Crypto


class Monero(Crypto):
    _display_name = "Monero XMR"
    default_fee = const.PRIO_NORMAL
    fixed_fee_steps = {
        const.PRIO_UNIMPORTANT: "Unimportant",
        const.PRIO_NORMAL: "Normal",
        const.PRIO_ELEVATED: "Elevated",
        const.PRIO_PRIORITY: "Priority",
    }
    precision = 12

    def __init__(self) -> None:
        self.crypto = "XMR"

        self.MONERO_WALLET_NAME = os.environ.get("MONERO_WALLET_NAME", "shkeeper")
        self.MONERO_WALLET_PASS = os.environ.get("MONERO_WALLET_PASS", "shkeeper")

        self.MONERO_DAEMON_HOST = os.environ.get("MONERO_DAEMON_HOST", "monerod")
        self.MONERO_DAEMON_PORT = os.environ.get("MONERO_DAEMON_PORT", "1111")
        self.MONERO_DAEMON_USER = os.environ.get("MONERO_DAEMON_USER", "monerod")
        self.MONERO_DAEMON_PASS = os.environ.get("MONERO_DAEMON_PASS", "monerod")

        self.MONERO_WALLET_RPC_HOST = os.environ.get(
            "MONERO_WALLET_RPC_HOST", "monero-wallet-rpc"
        )
        self.MONERO_WALLET_RPC_PORT = "2222"  # fix env clash with k8s env
        self.MONERO_WALLET_RPC_USER = os.environ.get(
            "MONERO_WALLET_RPC_USER", "shkeeper"
        )
        self.MONERO_WALLET_RPC_PASS = os.environ.get(
            "MONERO_WALLET_RPC_PASS", "shkeeper"
        )

    def getname(self):
        return "Monero"

    def gethost(self):
        return f"{self.MONERO_WALLET_RPC_HOST}:{self.MONERO_WALLET_RPC_PORT}"

    @property
    def monero_daemon(self):
        return Daemon(
            host=self.MONERO_DAEMON_HOST,
            port=self.MONERO_DAEMON_PORT,
            user=self.MONERO_DAEMON_USER,
            password=self.MONERO_DAEMON_PASS,
        )

    @property
    def monero_rpc_wallet(self):
        return JSONRPCWallet(
            host=self.MONERO_WALLET_RPC_HOST,
            port=self.MONERO_WALLET_RPC_PORT,
            user=self.MONERO_WALLET_RPC_USER,
            password=self.MONERO_WALLET_RPC_PASS,
        )

    @property
    def monero_wallet(self):
        return Wallet(self.monero_rpc_wallet)

    def balance(self) -> Decimal:
        try:
            return self.monero_wallet.balance(unlocked=True)
        except Exception:
            app.logger.exception("Can't get balance")
            return Decimal(0)

    def create_wallet(self):
        try:
            self.monero_rpc_wallet.raw_request(
                "create_wallet",
                {
                    "filename": self.MONERO_WALLET_NAME,
                    "password": self.MONERO_WALLET_PASS,
                    "language": "English",
                },
            )
        except RPCError as exception:
            if "Cannot create wallet. Already exists." not in str(exception):
                raise exception
        self.monero_rpc_wallet.raw_request(
            "open_wallet",
            {"filename": self.MONERO_WALLET_NAME, "password": self.MONERO_WALLET_PASS},
        )
        return {"error": None}

    def getstatus(self) -> str:
        try:
            info = self.monero_daemon.info()
            if info["status"] == "OK":
                if info["synchronized"]:
                    status = "Synced"
                else:
                    sync_status = "Syncing" if info["busy_syncing"] else "Sync pending"
                    status = f"{sync_status}: {info['target_height'] - info['height']} blocks behind"
            else:
                status = info["status"]
            return status
        except Exception:
            return "Offline"

    def mkaddr(self, **kwargs) -> str:
        address = self.monero_wallet.new_address()[0]
        return str(address)

    def getaddrbytx(
        self, txid
    ) -> List[Tuple[str, Decimal, int, Literal["send", "receive"]]]:
        res = self.monero_rpc_wallet.raw_request("get_transfer_by_txid", {"txid": txid})
        app.logger.debug(f"getaddrbytx: {res}")
        confirmations = res["transfer"].get("confirmations", 0)
        details = []
        for transfer in res["transfers"]:
            address = transfer["address"]
            amount = from_atomic(transfer["amount"])
            transfer_type = transfer["type"]
            if transfer_type == "in":
                operation = "receive"
            elif transfer_type == "out":
                operation = "send"
            else:
                operation = transfer_type
            details.append((address, amount, confirmations, operation))
        return details

    def get_confirmations_by_txid(self, txid) -> int:
        _, _, confirmations, _ = self.getaddrbytx(txid)[0]
        return confirmations

    def mkpayout(
        self,
        destination: str,
        amount: Decimal,
        fee: int,
        subtract_fee_from_amount: bool = False,
    ):
        try:
            priority_class = fee if fee in self.fixed_fee_steps else self.default_fee
            result = error = None
            if amount == self.balance():
                res_list = self.monero_wallet.sweep_all(
                    destination, priority=priority_class
                )
                result = [res[0].hash for res in res_list]
            else:
                txs = self.monero_wallet.transfer(
                    destination, amount, priority=priority_class
                )
                result = [tx.hash for tx in txs]
        except Exception as e:
            error = {"message": str(e)}
        return {"result": result, "error": error}

    def estimate_tx_fee(self, amount, **kwargs):
        if priority_class := kwargs.get("priority_class") is None:
            priority_class = self.default_fee

        fee = self.monero_wallet.transfer(
            self.monero_wallet.addresses()[0],
            amount,
            priority=priority_class,
            relay=False,
        )[0].fee
        app.logger.debug(
            f"Estimated fee for transfer of {amount} XMR with priority {priority_class} is {fee}"
        )
        return fee

    def dump_wallet(self) -> Tuple[str, str]:
        filename = "shkeeper-monero-mnemonic-key.txt"
        content = self.monero_rpc_wallet.raw_request(
            "query_key", {"key_type": "mnemonic"}
        )["key"]
        return filename, content

    def get_all_addresses(self) -> str:
        res = self.monero_rpc_wallet.raw_request("get_address")
        return [addr["address"] for addr in res["addresses"]]

    @property
    def wallet(self):
        return self._wallet.query.filter_by(crypto=self.crypto).first()
