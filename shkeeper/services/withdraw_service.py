# app/services/payout_service.py
from decimal import Decimal
import time
from urllib.parse import urlparse
from flask import current_app as app
from shkeeper import db
from shkeeper.models import Payout
from shkeeper.modules.classes.crypto import Crypto

class WithdrawService:
    @staticmethod
    def get_crypto(crypto_name: str):
        try:
            return Crypto.instances[crypto_name]
        except KeyError:
            raise ValueError(f"Unknown crypto: {crypto_name}")


    @staticmethod
    def create_payout_record(invoice_external_id, req, crypto_name, task_id=None, txids=None):
        destination = req[0]["dest"]
        return Payout.add(
            {
                "dest": destination,
                "amount": 0,
                "callback_url": False,
                "txids": txids or [],
            },
            crypto_name,
            task_id=task_id,
            external_id=str(f'withdraw***{invoice_external_id}***{crypto_name}***{req[0]["source"]}***{int(time.time())}')
        )

    @classmethod
    def single_withdraw(cls, crypto_name, req, invoice_external_id):
        crypto = cls.get_crypto(crypto_name)
        res = crypto.withdraw_to_external_wallet(req)
        task_id = res.get("task_id")
        cls.create_payout_record(invoice_external_id, req, crypto_name, task_id=task_id, txids=res.get("result", [], ))
        return res
