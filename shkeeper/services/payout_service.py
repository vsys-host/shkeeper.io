# app/services/payout_service.py
from decimal import Decimal
from urllib.parse import urlparse

from flask import current_app as app, g

from shkeeper import db
from shkeeper.models import Payout, UserRole
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.ethereum import Ethereum
from shkeeper.services.store_service import (
    effective_fee_percent,
    fee_collection_address,
    get_store_wallet,
)


class PayoutService:
    @staticmethod
    def get_crypto(crypto_name: str):
        try:
            return Crypto.instances[crypto_name]
        except KeyError:
            raise ValueError(f"Unknown crypto: {crypto_name}")

    @staticmethod
    def check_external_id_unique(req, crypto_name, store_id=None):
        external_id = req.get("external_id")
        if external_id:
            query = Payout.query.filter_by(crypto=crypto_name, external_id=external_id)
            if store_id is not None:
                query = query.filter_by(store_id=store_id)
            existing = query.first()
            if existing:
                raise ValueError(
                    f"Payout with this external_id already exists: {external_id}"
                )

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
    def create_payout_record(req, crypto_name, task_id=None, txids=None, store_id=None):
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
            external_id=req.get("external_id"),
            store_id=store_id,
        )

    @classmethod
    def _store_context(cls, crypto_name, store=None):
        store = store or getattr(g, "current_store", None)
        if not store:
            return store, {}
        sw = get_store_wallet(store, crypto_name)
        if not sw or not sw.fda_address:
            return store, {}
        crypto = cls.get_crypto(crypto_name)
        if isinstance(crypto, Ethereum):
            return store, {"from_account": sw.fda_address, "fda_key": sw.fda_key}
        return store, {}

    @classmethod
    def _normalize_addr(cls, addr: str) -> str:
        return (addr or "").strip().lower()

    @classmethod
    def enforce_store_owner_destination(cls, crypto_name, destination, store=None):
        """Non-admin store context may only payout to the configured cold wallet."""
        user = getattr(g, "user", None)
        store = store or getattr(g, "current_store", None)
        if not store or store.is_default:
            return destination
        if user and user.role == UserRole.ADMIN:
            return destination

        sw = get_store_wallet(store, crypto_name)
        cold = (sw.cold_wallet_address if sw else None) or ""
        cold = cold.strip()
        if not cold:
            raise ValueError(
                "Cold wallet address is not configured for this store/crypto. "
                "Ask the admin to set it before payout."
            )
        if cls._normalize_addr(destination) != cls._normalize_addr(cold):
            raise ValueError(
                f"Payout destination must be the configured cold wallet ({cold})"
            )
        return cold

    @classmethod
    def build_platform_fee_transfers(cls, store, crypto_name, gross_amount, destination):
        sw = get_store_wallet(store, crypto_name)
        fee_pct = effective_fee_percent(store, sw)
        fee_addr = fee_collection_address(store, sw, crypto_name)
        gross_amount = Decimal(gross_amount)

        if fee_pct > 0:
            if not fee_addr:
                raise ValueError(
                    f"Platform fee is {fee_pct}% but no fee collection address is "
                    f"configured for {crypto_name}. Set a per-store override or a "
                    f"global fee collection address."
                )
            fee_amount = (gross_amount * fee_pct / Decimal(100)).quantize(
                Decimal("0.00000001")
            )
            net_amount = gross_amount - fee_amount
            if net_amount <= 0:
                raise ValueError("Payout amount is too small after platform fee")
            transfers = []
            if fee_amount > 0:
                transfers.append({"dest": fee_addr, "amount": fee_amount})
            transfers.append({"dest": destination, "amount": net_amount})
            return transfers
        return [{"dest": destination, "amount": gross_amount}]

    @classmethod
    def single_payout(cls, crypto_name, req, apply_platform_fee=False):
        app.logger.info(
            f"[single_payout] Started for crypto={crypto_name} destination={req.get('destination')} amount={req.get('amount')} external_id={req.get('external_id')}"
        )

        store, source = cls._store_context(crypto_name)
        store_id = store.id if store else None

        try:
            crypto = cls.get_crypto(crypto_name)
            app.logger.info(f"[single_payout] Crypto instance resolved: {crypto_name}")
        except ValueError as e:
            app.logger.error(f"[single_payout] Unknown crypto: {crypto_name} — {e}")
            raise

        try:
            cls.check_external_id_unique(req, crypto_name, store_id=store_id)
        except ValueError as e:
            app.logger.warning(f"[single_payout] Duplicate external_id detected: {e}")
            raise

        callback_url = req.get("callback_url")
        cls.validate_callback_url(callback_url)

        destination = cls.enforce_store_owner_destination(
            crypto_name, req["destination"], store=store
        )
        amount = Decimal(req["amount"])

        if apply_platform_fee and store:
            transfers = cls.build_platform_fee_transfers(
                store, crypto_name, amount, destination
            )
            if len(transfers) > 1:
                # ETH has no Bitcoin-style atomic sendmany; sidecar sends one tx per
                # destination from the same FDA in a single multipayout task.
                return cls.multiple_payout(
                    crypto_name,
                    [
                        {
                            **transfer,
                            "external_id": req.get("external_id"),
                            "callback_url": callback_url,
                        }
                        for transfer in transfers
                    ],
                    store=store,
                    source=source,
                    enforce_destination=False,
                )

        app.logger.info(
            f"[single_payout] Calling mkpayout: destination={destination} amount={amount} fee={req['fee']}"
        )
        try:
            if source and isinstance(crypto, Ethereum):
                res = crypto.multipayout(
                    [{"dest": destination, "amount": amount}],
                    **source,
                )
            else:
                res = crypto.mkpayout(destination, amount, req["fee"])
        except Exception as e:
            app.logger.error(f"[single_payout] payout failed: {e}")
            raise

        app.logger.info(f"[single_payout] mkpayout response: {res}")

        try:
            payout = Payout.register_from_mkpayout(
                res,
                {
                    "dest": destination,
                    "amount": amount,
                    "callback_url": callback_url,
                },
                crypto_name,
                external_id=req.get("external_id"),
            )
        except Exception as e:
            app.logger.error(f"[single_payout] Failed to create payout record: {e}")
            raise

        if req.get("external_id") and isinstance(res, dict):
            res["external_id"] = req["external_id"]

        app.logger.info(
            f"[single_payout] Completed: payout_id={payout.id if payout else None} res={res}"
        )
        return res

    @classmethod
    def multiple_payout(
        cls, crypto_name, payout_list, store=None, source=None, enforce_destination=True
    ):
        if not isinstance(payout_list, list):
            raise ValueError("Expected an array of payouts")

        store = store or getattr(g, "current_store", None)
        store_id = store.id if store else None
        if source is None:
            _, source = cls._store_context(crypto_name, store=store)

        if enforce_destination:
            for req in payout_list:
                destination = cls.enforce_store_owner_destination(
                    crypto_name,
                    req.get("destination") or req.get("dest"),
                    store=store,
                )
                req["destination"] = destination
                req["dest"] = destination

        # Validate before calling the sidecar. Same external_id may appear more than
        # once in this batch (platform fee split: fee + net share one merchant id).
        seen_external_ids = set()
        for req in payout_list:
            cls.validate_callback_url(req.get("callback_url"))
            external_id = req.get("external_id")
            if external_id and external_id not in seen_external_ids:
                cls.check_external_id_unique(req, crypto_name, store_id=store_id)
                seen_external_ids.add(external_id)

        crypto = cls.get_crypto(crypto_name)
        if source and isinstance(crypto, Ethereum):
            res = crypto.multipayout(payout_list, **source)
        else:
            res = crypto.multipayout(payout_list)
        task_id = res.get("task_id")

        created_ids = []
        for req in payout_list:
            payout = cls.create_payout_record(
                req, crypto_name, task_id=task_id, store_id=store_id
            )
            created_ids.append(payout.id)
        res["external_ids"] = [
            req.get("external_id") for req in payout_list if req.get("external_id")
        ]
        return res
