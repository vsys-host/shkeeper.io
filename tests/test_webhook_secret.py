from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Blueprint, Flask, g
from werkzeug.exceptions import HTTPException

from shkeeper import db
from shkeeper import api_v1
from shkeeper.models import Setting
from shkeeper.services import webhook_hmac
from shkeeper.services import webhook_secret


class _SettingDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-only",
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.app_context = self.app.app_context()
        self.app_context.push()
        Setting.__table__.create(bind=db.engine)

        self.addCleanup(self._close_database)

    def _close_database(self) -> None:
        db.session.remove()
        self.app_context.pop()

    def _stored_secret(self) -> str | None:
        setting = Setting.query.get(webhook_secret.WEBHOOK_SECRET_SETTING_NAME)
        return setting.value if setting else None


class TestWebhookSecretService(_SettingDatabaseTestCase):
    def test_set_stores_one_global_setting_and_updates_it_in_place(self) -> None:
        webhook_secret.set_configured_webhook_secret("a" * 32)
        db.session.commit()

        self.assertEqual(self._stored_secret(), "a" * 32)
        self.assertEqual(
            Setting.query.filter_by(
                name=webhook_secret.WEBHOOK_SECRET_SETTING_NAME
            ).count(),
            1,
        )

        webhook_secret.set_configured_webhook_secret("b" * 32)
        db.session.commit()

        self.assertEqual(self._stored_secret(), "b" * 32)
        self.assertEqual(
            Setting.query.filter_by(
                name=webhook_secret.WEBHOOK_SECRET_SETTING_NAME
            ).count(),
            1,
        )

    def test_clear_removes_setting_and_restores_unconfigured_state(self) -> None:
        webhook_secret.set_configured_webhook_secret("a" * 32)
        db.session.commit()

        webhook_secret.clear_configured_webhook_secret()
        db.session.commit()

        self.assertIsNone(webhook_secret.get_configured_webhook_secret())
        self.assertEqual(
            Setting.query.filter_by(
                name=webhook_secret.WEBHOOK_SECRET_SETTING_NAME
            ).count(),
            0,
        )

    def test_generate_returns_candidate_without_persisting_it(self) -> None:
        candidate = "candidate-that-is-not-activated"

        with mock.patch.object(
            webhook_secret.secrets,
            "token_urlsafe",
            return_value=candidate,
        ) as token_urlsafe:
            generated = webhook_secret.generate_webhook_secret()

        self.assertEqual(generated, candidate)
        token_urlsafe.assert_called_once_with(32)
        self.assertIsNone(webhook_secret.get_configured_webhook_secret())

    def test_dedicated_secret_signs_body_without_exposing_api_key(self) -> None:
        body = b'{"exact":"body"}'
        dedicated_secret = "dedicated-secret"
        api_key = "api-key"

        with mock.patch.object(
            webhook_secret,
            "get_configured_webhook_secret",
            return_value=dedicated_secret,
        ):
            headers = webhook_secret.build_webhook_auth_headers(
                api_key,
                body,
                include_legacy_api_key=True,
            )

        self.assertIsNotNone(headers)
        assert headers is not None
        self.assertNotIn("X-Shkeeper-Api-Key", headers)
        timestamp = int(headers[webhook_hmac.WEBHOOK_TIMESTAMP_HEADER])
        signature = headers[webhook_hmac.WEBHOOK_SIGNATURE_HEADER]
        self.assertTrue(
            webhook_hmac.verify_webhook(
                dedicated_secret,
                body,
                timestamp=timestamp,
                signature_hex=signature,
                now=timestamp,
            )
        )
        self.assertFalse(
            webhook_hmac.verify_webhook(
                api_key,
                body,
                timestamp=timestamp,
                signature_hex=signature,
                now=timestamp,
            )
        )

    def test_fallback_signs_with_and_can_include_api_key(self) -> None:
        body = b'{"exact":"body"}'
        api_key = "legacy-api-key"

        with mock.patch.object(
            webhook_secret,
            "get_configured_webhook_secret",
            return_value=None,
        ):
            headers = webhook_secret.build_webhook_auth_headers(
                api_key,
                body,
                include_legacy_api_key=True,
            )

        self.assertIsNotNone(headers)
        assert headers is not None
        self.assertEqual(headers["X-Shkeeper-Api-Key"], api_key)
        timestamp = int(headers[webhook_hmac.WEBHOOK_TIMESTAMP_HEADER])
        self.assertTrue(
            webhook_hmac.verify_webhook(
                api_key,
                body,
                timestamp=timestamp,
                signature_hex=headers[webhook_hmac.WEBHOOK_SIGNATURE_HEADER],
                now=timestamp,
            )
        )

    def test_no_secret_and_no_api_key_produces_no_auth_headers(self) -> None:
        with mock.patch.object(
            webhook_secret,
            "get_configured_webhook_secret",
            return_value=None,
        ):
            headers = webhook_secret.build_webhook_auth_headers(
                None,
                b"{}",
                include_legacy_api_key=True,
            )

        self.assertIsNone(headers)


class TestWebhookSecretApi(_SettingDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()

        auth_blueprint = Blueprint("auth", __name__ + "_auth")
        auth_blueprint.add_url_rule("/login", "login", lambda: "login")
        self.app.register_blueprint(auth_blueprint)

        self.crypto = SimpleNamespace(
            wallet=SimpleNamespace(apikey="legacy-api-key")
        )
        self.crypto_instances = mock.patch.object(
            api_v1.Crypto,
            "instances",
            {"BTC": self.crypto},
        )
        self.crypto_instances.start()
        self.addCleanup(self.crypto_instances.stop)

    def _call(
        self,
        view,
        *,
        method: str = "GET",
        json_body=...,
        data: str | None = None,
        content_type: str | None = None,
        authenticated: bool = True,
    ):
        request_kwargs = {"method": method}
        if json_body is not ...:
            request_kwargs["json"] = json_body
        if data is not None:
            request_kwargs["data"] = data
        if content_type is not None:
            request_kwargs["content_type"] = content_type

        with self.app.test_request_context(
            "/api/v1/BTC/payment-gateway/webhook-secret",
            **request_kwargs,
        ):
            g.user = object() if authenticated else None
            try:
                result = view(crypto_name="BTC")
            except HTTPException as exc:
                return exc.get_response()
            return self.app.make_response(result)

    def assertNoStore(self, response) -> None:
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_control.lower())

    def test_get_reports_status_without_disclosing_stored_secret(self) -> None:
        secret = "s" * 32
        webhook_secret.set_configured_webhook_secret(secret)
        db.session.commit()

        response = self._call(api_v1.payment_gateway_get_webhook_secret)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "status": "success",
                "configured": True,
                "fallback": None,
            },
        )
        self.assertNotIn(secret, response.get_data(as_text=True))

    def test_get_reports_api_key_fallback_when_not_configured(self) -> None:
        response = self._call(api_v1.payment_gateway_get_webhook_secret)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "status": "success",
                "configured": False,
                "fallback": "api_key",
            },
        )

    def test_generate_returns_unpersisted_candidate_with_no_store(self) -> None:
        response = self._call(
            api_v1.payment_gateway_set_webhook_secret,
            method="POST",
            json_body={"action": "generate"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["active"])
        self.assertIsInstance(payload["generated_secret"], str)
        self.assertGreaterEqual(
            len(payload["generated_secret"]),
            webhook_secret.MIN_WEBHOOK_SECRET_LENGTH,
        )
        self.assertIsNone(webhook_secret.get_configured_webhook_secret())
        self.assertNoStore(response)

    def test_generate_does_not_replace_an_active_secret(self) -> None:
        active_secret = "a" * webhook_secret.MIN_WEBHOOK_SECRET_LENGTH
        webhook_secret.set_configured_webhook_secret(active_secret)
        db.session.commit()

        response = self._call(
            api_v1.payment_gateway_set_webhook_secret,
            method="POST",
            json_body={"action": "generate"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["configured"])
        self.assertFalse(response.get_json()["active"])
        self.assertEqual(
            webhook_secret.get_configured_webhook_secret(),
            active_secret,
        )

    def test_set_activates_exact_secret_and_does_not_echo_it(self) -> None:
        secret = " " + ("m" * (webhook_secret.MIN_WEBHOOK_SECRET_LENGTH - 2)) + " "

        response = self._call(
            api_v1.payment_gateway_set_webhook_secret,
            method="POST",
            json_body={"action": "set", "secret": secret},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["configured"])
        self.assertEqual(webhook_secret.get_configured_webhook_secret(), secret)
        self.assertNotIn(secret, response.get_data(as_text=True))

    def test_delete_clears_secret_and_restores_api_key_fallback(self) -> None:
        webhook_secret.set_configured_webhook_secret("s" * 32)
        db.session.commit()

        response = self._call(
            api_v1.payment_gateway_delete_webhook_secret,
            method="DELETE",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "status": "success",
                "configured": False,
                "fallback": "api_key",
            },
        )
        self.assertIsNone(webhook_secret.get_configured_webhook_secret())

    def test_post_rejects_non_json_null_and_list_payloads(self) -> None:
        cases = (
            (
                "text/plain",
                {
                    "data": '{"action":"generate"}',
                    "content_type": "text/plain",
                },
                415,
            ),
            (
                "json null",
                {
                    "data": "null",
                    "content_type": "application/json",
                },
                400,
            ),
            (
                "json list",
                {"json_body": [{"action": "generate"}]},
                400,
            ),
        )

        for label, request_kwargs, expected_status in cases:
            with self.subTest(label=label):
                response = self._call(
                    api_v1.payment_gateway_set_webhook_secret,
                    method="POST",
                    **request_kwargs,
                )
                self.assertEqual(response.status_code, expected_status)
                self.assertIsNone(webhook_secret.get_configured_webhook_secret())

    def test_post_rejects_invalid_action_and_secret_lengths(self) -> None:
        cases = (
            {"action": "unknown"},
            {"action": "set", "secret": "too-short"},
            {
                "action": "set",
                "secret": "x" * (webhook_secret.MAX_WEBHOOK_SECRET_LENGTH + 1),
            },
        )

        for payload in cases:
            with self.subTest(payload=payload):
                response = self._call(
                    api_v1.payment_gateway_set_webhook_secret,
                    method="POST",
                    json_body=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIsNone(webhook_secret.get_configured_webhook_secret())

    def test_endpoint_remains_login_protected_without_session_transaction(self) -> None:
        response = self._call(
            api_v1.payment_gateway_get_webhook_secret,
            authenticated=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))


if __name__ == "__main__":
    unittest.main()
