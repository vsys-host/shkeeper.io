# app/services/payout_service.py
from decimal import Decimal
from flask import current_app as app
from shkeeper import db
from shkeeper.models import Payout
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.tasks import schedule_task_polling

class PayoutService:
    @staticmethod
    def get_crypto(crypto_name: str):
        try:
            return Crypto.instances[crypto_name]
        except KeyError:
            raise ValueError(f"Unknown crypto: {crypto_name}")

    @staticmethod
    def check_external_id_unique(req, crypto_name):
        external_id = req.get("external_id")
        if external_id:
            existing = Payout.query.filter_by(crypto=crypto_name, external_id=external_id).first()
            if existing:
                raise ValueError(f"Payout with this external_id already exists: {external_id}")

    @staticmethod
    def create_payout_record(req, crypto_name, task_id=None, txids=None):
        destination = req.get("destination") or req.get("dest")
        return Payout.add(
            {
                "dest": destination,
                "amount": Decimal(req["amount"]),
                "callback_url": req.get("callback_url"),
                "txids": txids or [],
            },
            crypto_name,
            task_id=task_id,
            external_id=req.get("external_id")
        )

    @classmethod
    def single_payout(cls, crypto_name, req):
        crypto = cls.get_crypto(crypto_name)
        cls.check_external_id_unique(req, crypto_name)

        res = crypto.mkpayout(
            req["destination"],
            Decimal(req["amount"]),
            req["fee"],
        )
        task_id = res.get("task_id")
        cls.create_payout_record(req, crypto_name, task_id=task_id, txids=res.get("result", []))

        if task_id:
            schedule_task_polling(crypto_name, task_id)
        if app.config.get("ENABLE_PAYOUT_CALLBACK") and req.get("external_id"):
            res["external_id"] = req["external_id"]

        return res

    @classmethod
    def multiple_payout(cls, crypto_name, payout_list):
        if not isinstance(payout_list, list):
            raise ValueError("Expected an array of payouts")

        crypto = cls.get_crypto(crypto_name)
        res = crypto.multipayout(payout_list)
        task_id = res.get("task_id")

        created_ids = []
        for req in payout_list:
            cls.check_external_id_unique(req, crypto_name)
            payout = cls.create_payout_record(req, crypto_name, task_id=task_id)
            created_ids.append(payout.id)

        if task_id:
            for pid in created_ids:
                p = Payout.query.get(pid)
                p.task_id = task_id
            db.session.commit()
            schedule_task_polling(crypto_name, task_id)
        if app.config.get("ENABLE_PAYOUT_CALLBACK"):
            res["external_ids"] = [
                req.get("external_id")
                for req in payout_list
                if req.get("external_id")
            ]
        return res
