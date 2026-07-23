from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from flask import Flask

from shkeeper import callback, db
from shkeeper.models import FeeCalculationPolicy, InvoiceStatus, Setting
from shkeeper.services import webhook_hmac, webhook_secret


class TestWebhookCallbackAuthentication(unittest.TestCase):
    API_KEY = "legacy-api-key"
    DEDICATED_SECRET = "dedicated-webhook-secret"

    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            REQUESTS_NOTIFICATION_TIMEOUT=17,
        )
        db.init_app(self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        Setting.__table__.create(bind=db.engine)
        self.addCleanup(self._close_database)

    def _close_database(self) -> None:
        db.session.remove()
        self.app_context.pop()

    def _configure(self, dedicated: bool) -> str:
        existing = Setting.query.get(webhook_secret.WEBHOOK_SECRET_SETTING_NAME)
        if existing is not None:
            db.session.delete(existing)
            db.session.commit()

        if dedicated:
            webhook_secret.set_configured_webhook_secret(self.DEDICATED_SECRET)
            db.session.commit()
            return self.DEDICATED_SECRET
        return self.API_KEY

    def _assert_request_authentication(
        self,
        post: mock.Mock,
        *,
        signing_secret: str,
        dedicated: bool,
        legacy_header_in_fallback: bool = True,
    ) -> None:
        post.assert_called_once()
        kwargs = post.call_args.kwargs
        body = kwargs["data"]
        headers = kwargs["headers"]

        self.assertIsInstance(body, bytes)
        self.assertEqual(headers["Content-Type"], "application/json")
        timestamp = int(headers[webhook_hmac.WEBHOOK_TIMESTAMP_HEADER])
        signature = headers[webhook_hmac.WEBHOOK_SIGNATURE_HEADER]
        self.assertTrue(
            webhook_hmac.verify_webhook(
                signing_secret,
                body,
                timestamp=timestamp,
                signature_hex=signature,
                now=timestamp,
            )
        )

        if dedicated:
            self.assertNotIn("X-Shkeeper-Api-Key", headers)
            self.assertFalse(
                webhook_hmac.verify_webhook(
                    self.API_KEY,
                    body,
                    timestamp=timestamp,
                    signature_hex=signature,
                    now=timestamp,
                )
            )
        elif legacy_header_in_fallback:
            self.assertEqual(headers["X-Shkeeper-Api-Key"], self.API_KEY)
        else:
            self.assertNotIn("X-Shkeeper-Api-Key", headers)

    def _send_unconfirmed(self, dedicated: bool) -> None:
        signing_secret = self._configure(dedicated)
        wallet = SimpleNamespace(apikey=self.API_KEY)
        crypto = SimpleNamespace(wallet=wallet, precision=8)
        invoice_address = SimpleNamespace(invoice_id=5)
        invoice = SimpleNamespace(
            external_id="order-1",
            callback_url="https://merchant.example/unconfirmed",
        )
        utx = SimpleNamespace(
            crypto="BTC",
            txid="tx-unconfirmed",
            addr="bc1-address",
            amount_crypto=Decimal("1.25"),
            callback_confirmed=False,
        )

        invoice_address_query = mock.Mock()
        invoice_address_query.filter_by.return_value.first.return_value = (
            invoice_address
        )
        invoice_query = mock.Mock()
        invoice_query.filter_by.return_value.first.return_value = invoice
        post = mock.Mock(
            return_value=SimpleNamespace(status_code=202, reason="Accepted")
        )

        with (
            mock.patch.object(
                callback,
                "InvoiceAddress",
                SimpleNamespace(query=invoice_address_query),
            ),
            mock.patch.object(
                callback,
                "Invoice",
                SimpleNamespace(query=invoice_query),
            ),
            mock.patch.object(callback.Crypto, "instances", {"BTC": crypto}),
            mock.patch.object(callback.requests, "post", post),
        ):
            result = callback.send_unconfirmed_notification(utx)

        self.assertTrue(result)
        self.assertTrue(utx.callback_confirmed)
        self.assertEqual(
            post.call_args.args[0],
            "https://merchant.example/unconfirmed",
        )
        self.assertEqual(
            post.call_args.kwargs["timeout"],
            self.app.config["REQUESTS_NOTIFICATION_TIMEOUT"],
        )
        self._assert_request_authentication(
            post,
            signing_secret=signing_secret,
            dedicated=dedicated,
        )

    def _send_confirmed(self, dedicated: bool) -> None:
        signing_secret = self._configure(dedicated)
        wallet = SimpleNamespace(apikey=self.API_KEY)
        crypto = SimpleNamespace(wallet=wallet)
        rate = SimpleNamespace(
            get_orig_amount=lambda amount: amount - Decimal("0.5"),
            fee=Decimal("1"),
            fixed_fee=Decimal("0"),
            fee_policy=FeeCalculationPolicy.PERCENT_FEE,
        )
        tx = SimpleNamespace(
            id=7,
            txid="tx-confirmed",
            created_at=datetime(2026, 1, 2, 3, 4, 5),
            amount_crypto=Decimal("1.25"),
            amount_fiat=Decimal("100"),
            rate=rate,
            crypto="BTC",
            callback_confirmed=False,
        )
        tx.invoice = SimpleNamespace(
            transactions=[tx],
            external_id="order-2",
            crypto="BTC",
            addr="bc1-address",
            fiat="USD",
            balance_fiat=Decimal("100"),
            balance_crypto=Decimal("1.25"),
            status=InvoiceStatus.PAID,
            rate=rate,
            amount_fiat=Decimal("100"),
            wallet=SimpleNamespace(ulimit=Decimal("105")),
            callback_url="https://merchant.example/confirmed",
        )
        post = mock.Mock(
            return_value=SimpleNamespace(status_code=202, reason="Accepted")
        )

        with (
            mock.patch.object(callback.Crypto, "instances", {"BTC": crypto}),
            mock.patch.object(callback.requests, "post", post),
        ):
            result = callback.send_notification(tx)

        self.assertTrue(result)
        self.assertTrue(tx.callback_confirmed)
        self.assertEqual(
            post.call_args.args[0],
            "https://merchant.example/confirmed",
        )
        self._assert_request_authentication(
            post,
            signing_secret=signing_secret,
            dedicated=dedicated,
        )

    def _send_payout(self, dedicated: bool) -> None:
        signing_secret = self._configure(dedicated)
        wallet = SimpleNamespace(apikey=self.API_KEY)
        crypto = SimpleNamespace(wallet=wallet)
        payout = SimpleNamespace(
            id=9,
            external_id="payout-1",
            transactions=[SimpleNamespace(txid="tx-payout")],
            amount=Decimal("2.5"),
            crypto="BTC",
            created_at=datetime(2026, 2, 3, 4, 5, 6),
            callback_url="https://merchant.example/payout",
        )
        notif = SimpleNamespace(
            object_id=payout.id,
            retries=0,
            message=None,
            callback_confirmed=False,
        )
        payout_query = mock.Mock()
        payout_query.get.return_value = payout
        rate = SimpleNamespace(get_rate=lambda: Decimal("50000"))
        exchange_rate = SimpleNamespace(get=mock.Mock(return_value=rate))
        post = mock.Mock(
            return_value=SimpleNamespace(status_code=202, reason="Accepted")
        )

        with (
            mock.patch.object(
                callback,
                "Payout",
                SimpleNamespace(query=payout_query),
            ),
            mock.patch.object(callback, "ExchangeRate", exchange_rate),
            mock.patch.object(callback.Crypto, "instances", {"BTC": crypto}),
            mock.patch.object(callback.requests, "post", post),
        ):
            result = callback.send_payout_notification(notif)

        self.assertTrue(result)
        self.assertTrue(notif.callback_confirmed)
        self.assertEqual(
            post.call_args.args[0],
            "https://merchant.example/payout",
        )
        self._assert_request_authentication(
            post,
            signing_secret=signing_secret,
            dedicated=dedicated,
            legacy_header_in_fallback=False,
        )

    def test_unconfirmed_callback_uses_dedicated_secret(self) -> None:
        self._send_unconfirmed(dedicated=True)

    def test_unconfirmed_callback_preserves_api_key_fallback(self) -> None:
        self._send_unconfirmed(dedicated=False)

    def test_confirmed_callback_uses_dedicated_secret(self) -> None:
        self._send_confirmed(dedicated=True)

    def test_confirmed_callback_preserves_api_key_fallback(self) -> None:
        self._send_confirmed(dedicated=False)

    def test_payout_callback_uses_dedicated_secret(self) -> None:
        self._send_payout(dedicated=True)

    def test_payout_callback_preserves_api_key_fallback(self) -> None:
        self._send_payout(dedicated=False)


if __name__ == "__main__":
    unittest.main()
