# app/services/payout_service.py
from decimal import Decimal
from urllib.parse import urlparse
from flask import current_app as app
from shkeeper import db
from shkeeper.models import Payout
from shkeeper.modules.classes.crypto import Crypto

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
    def validate_callback_url(callback_url):
        if not callback_url:
            return
        parsed = urlparse(callback_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid callback_url: {callback_url}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid callback_url scheme: {callback_url}")

    @staticmethod
    def create_payout_record(req, crypto_name, task_id=None, txids=None):
        destination = req.get("destination") or req.get("dest")
        callback_url = req.get("callback_url")
        PayoutService.validate_callback_url(callback_url)
        return Payout.add(
            {
                "dest": destination,
                "amount": Decimal(req["amount"]),
                "callback_url": callback_url,
                "txids": txids or [],
            },
            crypto_name,
            task_id=task_id,
            external_id=req.get("external_id")
        )

    @classmethod
    def single_payout(cls, crypto_name, req):
        app.logger.info(f"[single_payout] Started for crypto={crypto_name} destination={req.get('destination')} amount={req.get('amount')} external_id={req.get('external_id')}")

        try:
            crypto = cls.get_crypto(crypto_name)
            app.logger.info(f"[single_payout] Crypto instance resolved: {crypto_name}")
        except ValueError as e:
            app.logger.error(f"[single_payout] Unknown crypto: {crypto_name} — {e}")
            raise

        try:
            cls.check_external_id_unique(req, crypto_name)
            app.logger.info(f"[single_payout] external_id uniqueness check passed for external_id={req.get('external_id')}")
        except ValueError as e:
            app.logger.warning(f"[single_payout] Duplicate external_id detected: {e}")
            raise

        callback_url = req.get("callback_url")
        try:
            cls.validate_callback_url(callback_url)
            app.logger.info(f"[single_payout] callback_url validated: {callback_url!r}")
        except ValueError as e:
            app.logger.error(f"[single_payout] Invalid callback_url={callback_url!r}: {e}")
            raise

        app.logger.info(f"[single_payout] Calling mkpayout: destination={req['destination']} amount={req['amount']} fee={req['fee']}")
        try:
            res = crypto.mkpayout(
                req["destination"],
                Decimal(req["amount"]),
                req["fee"],
            )
        except Exception as e:
            app.logger.error(f"[single_payout] mkpayout failed: {e}")
            raise

        task_id = res.get("task_id")
        txids = res.get("result", [])
        app.logger.info(f"[single_payout] mkpayout response: task_id={task_id} txids={txids} full_response={res}")

        if not task_id:
            app.logger.warning(f"[single_payout] No task_id returned from mkpayout — payout will rely on txid-based confirmation only")

        if not txids:
            app.logger.warning(f"[single_payout] No txids in mkpayout result — PayoutTx will be empty until task resolves")

        try:
            payout = cls.create_payout_record(req, crypto_name, task_id=task_id, txids=txids)
            app.logger.info(f"[single_payout] Payout record created: payout_id={payout.id} task_id={task_id} txids={txids}")
        except Exception as e:
            app.logger.error(f"[single_payout] Failed to create payout record: {e}")
            raise

        if req.get("external_id"):
            res["external_id"] = req["external_id"]

        app.logger.info(f"[single_payout] Completed successfully: payout_id={payout.id} external_id={res.get('external_id')} task_id={task_id}")
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
            cls.validate_callback_url(req.get("callback_url"))
            payout = cls.create_payout_record(req, crypto_name, task_id=task_id)
            created_ids.append(payout.id)
        res["external_ids"] = [
            req.get("external_id")
            for req in payout_list
            if req.get("external_id")
        ]
        return res
