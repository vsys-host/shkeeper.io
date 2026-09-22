from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Flask, g
from werkzeug.exceptions import Forbidden

from shkeeper.models import UserRole
from shkeeper.services.tenancy import require_admin, require_default_store


class TestDumpAccessControl(unittest.TestCase):
    def setUp(self) -> None:
        self._flask_app = Flask(__name__)
        self._app_ctx = self._flask_app.app_context()
        self._app_ctx.push()
        self.addCleanup(self._app_ctx.pop)

    def test_require_admin_rejects_store_owner(self) -> None:
        g.user = SimpleNamespace(role=UserRole.STORE_OWNER)
        with self.assertRaises(Forbidden):
            require_admin()

    def test_require_admin_allows_admin(self) -> None:
        g.user = SimpleNamespace(role=UserRole.ADMIN)
        require_admin()

    def test_require_default_store_rejects_other_store(self) -> None:
        g.current_store = SimpleNamespace(is_default=False, id=2)
        with self.assertRaises(Forbidden):
            require_default_store()

    def test_require_default_store_allows_store_one(self) -> None:
        g.current_store = SimpleNamespace(is_default=True, id=1)
        require_default_store()

    def test_backup_rejects_store_owner_even_on_store_one(self) -> None:
        from shkeeper.api_v1 import backup

        with self._flask_app.test_request_context("/api/v1/BTC/backup"):
            g.user = SimpleNamespace(role=UserRole.STORE_OWNER)
            g.current_store = SimpleNamespace(is_default=True, id=1)
            with self.assertRaises(Forbidden):
                backup(crypto_name="BTC")

    def test_backup_admin_on_non_default_store_still_dumps(self) -> None:
        from shkeeper.api_v1 import backup

        class FakeBtc:
            def dump_wallet(self, store_id=None):
                self.store_id = store_id
                return ("wallet.json", "{}")

        fake = FakeBtc()
        with mock.patch("shkeeper.api_v1.Btc", FakeBtc):
            with mock.patch.dict(
                "shkeeper.api_v1.Crypto.instances", {"BTC": fake}, clear=True
            ):
                with self._flask_app.test_request_context("/api/v1/BTC/backup"):
                    g.user = SimpleNamespace(role=UserRole.ADMIN)
                    g.current_store = SimpleNamespace(is_default=False, id=2)
                    response = backup(crypto_name="BTC")
        self.assertIsNone(fake.store_id)
        self.assertEqual(response.status_code, 200)

    def test_backup_admin_dumps_without_store_id(self) -> None:
        from shkeeper.api_v1 import backup

        class FakeBtc:
            def dump_wallet(self, store_id=None):
                self.store_id = store_id
                return ("wallet.json", "{}")

        fake = FakeBtc()
        with mock.patch("shkeeper.api_v1.Btc", FakeBtc):
            with mock.patch.dict(
                "shkeeper.api_v1.Crypto.instances", {"BTC": fake}, clear=True
            ):
                with self._flask_app.test_request_context("/api/v1/BTC/backup"):
                    g.user = SimpleNamespace(role=UserRole.ADMIN)
                    g.current_store = SimpleNamespace(is_default=True, id=1)
                    response = backup(crypto_name="BTC")
        self.assertIsNone(fake.store_id)
        self.assertEqual(response.status_code, 200)

    def test_backup_rejects_api_key_auth(self) -> None:
        from shkeeper.api_v1 import backup

        with self._flask_app.test_request_context(
            "/api/v1/BTC/backup",
            headers={"X-Shkeeper-Api-Key": "store-key"},
        ):
            g.user = None
            result = backup(crypto_name="BTC")
        self.assertEqual(
            result["message"],
            "This endpoint doesn't accept X-Shkeeper-Api-Key auth",
        )
