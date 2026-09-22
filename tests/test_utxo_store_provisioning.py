from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Flask

from shkeeper.models import StoreWalletStatus
from shkeeper.services.multistore import store_wallet_is_ready, uses_fee_deposit_account


class _AppContextTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._flask_app = Flask(__name__)
        self._app_ctx = self._flask_app.app_context()
        self._app_ctx.push()
        self.addCleanup(self._app_ctx.pop)


class TestStoreWalletIsReady(unittest.TestCase):
    def test_missing_wallet_is_not_ready(self) -> None:
        self.assertFalse(store_wallet_is_ready(None, mock.Mock()))

    def test_utxo_ready_without_fda(self) -> None:
        sw = SimpleNamespace(
            status=StoreWalletStatus.READY, fda_address=None, crypto="BTC"
        )
        with mock.patch(
            "shkeeper.services.multistore.uses_fee_deposit_account", return_value=False
        ):
            self.assertTrue(store_wallet_is_ready(sw, mock.Mock()))

    def test_eth_ready_requires_fda(self) -> None:
        sw = SimpleNamespace(
            status=StoreWalletStatus.READY, fda_address=None, crypto="ETH"
        )
        with mock.patch(
            "shkeeper.services.multistore.uses_fee_deposit_account", return_value=True
        ):
            self.assertFalse(store_wallet_is_ready(sw, mock.Mock()))

    def test_eth_ready_with_fda(self) -> None:
        sw = SimpleNamespace(
            status=StoreWalletStatus.READY,
            fda_address="0xabc",
            crypto="ETH",
        )
        with mock.patch(
            "shkeeper.services.multistore.uses_fee_deposit_account", return_value=True
        ):
            self.assertTrue(store_wallet_is_ready(sw, mock.Mock()))

    def test_failed_utxo_is_not_ready(self) -> None:
        sw = SimpleNamespace(
            status=StoreWalletStatus.FAILED, fda_address=None, crypto="BTC"
        )
        with mock.patch(
            "shkeeper.services.multistore.uses_fee_deposit_account", return_value=False
        ):
            self.assertFalse(store_wallet_is_ready(sw, mock.Mock()))

    def test_unresolved_eth_requires_fda(self) -> None:
        from shkeeper.modules.classes.crypto import Crypto

        sw = SimpleNamespace(
            status=StoreWalletStatus.READY, fda_address=None, crypto="ETH"
        )
        with mock.patch.dict(Crypto.instances, {}, clear=True):
            self.assertFalse(store_wallet_is_ready(sw))

    def test_unresolved_btc_is_ready_without_fda(self) -> None:
        from shkeeper.modules.classes.crypto import Crypto

        sw = SimpleNamespace(
            status=StoreWalletStatus.READY, fda_address=None, crypto="BTC"
        )
        with mock.patch.dict(Crypto.instances, {}, clear=True):
            self.assertTrue(store_wallet_is_ready(sw))


class TestUsesFeeDepositAccount(unittest.TestCase):
    def test_none_is_false(self) -> None:
        self.assertFalse(uses_fee_deposit_account(None))


class TestProvisionNetworkUtxo(_AppContextTestCase):
    @mock.patch("shkeeper.services.store_service.db")
    @mock.patch(
        "shkeeper.services.store_service.uses_fee_deposit_account", return_value=False
    )
    def test_marks_ready_without_calling_sidecar(self, _uses_fda, db) -> None:
        from shkeeper.services.store_service import _provision_network

        sw = mock.Mock()
        crypto = mock.Mock()
        crypto.mkaddr.side_effect = AssertionError("mkaddr should not be called")
        crypto.create_fee_deposit_account.side_effect = AssertionError(
            "create_fee_deposit_account should not be called"
        )

        _provision_network(mock.Mock(id=2), "BTC", [(sw, crypto)])

        crypto.mkaddr.assert_not_called()
        crypto.create_fee_deposit_account.assert_not_called()
        self.assertIsNone(sw.fda_address)
        self.assertEqual(sw.status, StoreWalletStatus.READY)
        self.assertIsNone(sw.last_error)
        db.session.commit.assert_called_once()

    @mock.patch("shkeeper.services.store_service.StoreWallet")
    @mock.patch("shkeeper.services.store_service.db")
    @mock.patch(
        "shkeeper.services.store_service.uses_fee_deposit_account", return_value=True
    )
    def test_eth_still_creates_fda(self, _uses_fda, db, StoreWallet) -> None:
        from shkeeper.services.store_service import _provision_network

        StoreWallet.query.filter_by.return_value.all.return_value = []
        sw = mock.Mock(fda_address=None)
        crypto = mock.Mock()
        crypto.create_fee_deposit_account.return_value = "0xfda"
        store = mock.Mock(id=2)

        _provision_network(store, "ETH", [(sw, crypto)])

        crypto.create_fee_deposit_account.assert_called_once_with(store_id=2)
        self.assertEqual(sw.fda_address, "0xfda")
        self.assertEqual(sw.status, StoreWalletStatus.READY)
