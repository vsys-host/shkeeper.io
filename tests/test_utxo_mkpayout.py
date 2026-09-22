from __future__ import annotations

import unittest
from decimal import Decimal
from unittest import mock

from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto


class _UtxoCrypto:
    crypto = "DOGE"
    network_currency = "DOGE"


class TestPayoutFeeCoin(unittest.TestCase):
    def test_uses_total_satoshis_when_below_amount(self) -> None:
        crypto = _UtxoCrypto()
        fee_coin = UtxoLikeWalletCrypto._payout_fee_coin(
            crypto,
            {"fee": 11_394_050, "fee_satoshi": 50_416},
            Decimal("0.50159216"),
        )
        self.assertEqual(fee_coin, Decimal("0.11394050"))

    def test_falls_back_to_rate_times_size_when_fee_is_sat_per_kb(self) -> None:
        crypto = _UtxoCrypto()
        amount = Decimal("0.50159216")
        # Old sidecar returned sat/kB in `fee` (~0.504 DOGE), larger than the send amount.
        fee_coin = UtxoLikeWalletCrypto._payout_fee_coin(
            crypto,
            {"fee": 50_416_153, "fee_satoshi": 50_416},
            amount,
        )
        self.assertLess(fee_coin, amount)
        self.assertEqual(fee_coin, Decimal("50416") * Decimal("226") / Decimal("100000000"))


class TestUtxoMkpayout(unittest.TestCase):
    def setUp(self) -> None:
        self.crypto = _UtxoCrypto()
        self.crypto.estimate_tx_fee = mock.Mock()
        self.crypto._api_post = mock.Mock(return_value={"task_id": "t1"})
        self.crypto._payout_fee_coin = lambda est, amt: UtxoLikeWalletCrypto._payout_fee_coin(
            self.crypto, est, amt
        )

    def test_subtracts_size_based_fee_and_sends_remainder(self) -> None:
        amount = Decimal("0.50159216")
        self.crypto.estimate_tx_fee.return_value = {
            "fee": 11_394_050,
            "fee_satoshi": 50_416,
        }
        res = UtxoLikeWalletCrypto.mkpayout(
            self.crypto,
            "DTxkg653MQDt7cihyf19xX7EuqUzjL2TZs",
            amount,
            "",
            subtract_fee_from_amount=True,
            store_id=1,
        )
        self.assertEqual(res, {"task_id": "t1"})
        sent_amount = self.crypto._api_post.call_args.args[0]
        self.assertIn("/0.38765166/", sent_amount)
        self.assertTrue(sent_amount.endswith("/50416"))
        self.crypto.estimate_tx_fee.assert_called_once()
        self.assertEqual(
            self.crypto.estimate_tx_fee.call_args.kwargs.get("destination"),
            "DTxkg653MQDt7cihyf19xX7EuqUzjL2TZs",
        )

    def test_old_sat_per_kb_estimate_does_not_block_half_doge(self) -> None:
        amount = Decimal("0.50159216")
        self.crypto.estimate_tx_fee.return_value = {
            "fee": 50_416_153,
            "fee_satoshi": 50_416,
        }
        res = UtxoLikeWalletCrypto.mkpayout(
            self.crypto,
            "DTxkg653MQDt7cihyf19xX7EuqUzjL2TZs",
            amount,
            None,
            subtract_fee_from_amount=True,
            store_id=1,
        )
        self.assertEqual(res, {"task_id": "t1"})
        self.assertNotIn("Payout failed", str(res))

    def test_rejects_when_true_fee_covers_the_amount(self) -> None:
        self.crypto.estimate_tx_fee.return_value = {
            "fee": 60_000_000,
            "fee_satoshi": 0,
        }
        res = UtxoLikeWalletCrypto.mkpayout(
            self.crypto,
            "DTxkg653MQDt7cihyf19xX7EuqUzjL2TZs",
            Decimal("0.50"),
            "",
            subtract_fee_from_amount=True,
            store_id=1,
        )
        self.assertIn("Need 0.6 fee", res)
        self.crypto._api_post.assert_not_called()


class TestUtxoGetaddrbytx(unittest.TestCase):
    def setUp(self) -> None:
        from flask import Flask

        self._flask_app = Flask(__name__)
        self._app_ctx = self._flask_app.app_context()
        self._app_ctx.push()
        self.addCleanup(self._app_ctx.pop)
        self.crypto = _UtxoCrypto()
        self.crypto._api_post = mock.Mock()
        self.crypto._store_payload = lambda store_id=None: (
            UtxoLikeWalletCrypto._store_payload(self.crypto, store_id)
        )
        self.crypto._crypto_store_ids = lambda store_id=None: (
            UtxoLikeWalletCrypto._crypto_store_ids(self.crypto, store_id)
        )
        self.crypto.getaddrbytx = lambda tx, store_id=None: (
            UtxoLikeWalletCrypto.getaddrbytx(self.crypto, tx, store_id=store_id)
        )

    def test_passes_store_id_to_sidecar(self) -> None:
        self.crypto._api_post.return_value = [["tb1qone", "0.1", 3, "receive"]]
        result = UtxoLikeWalletCrypto.getaddrbytx(
            self.crypto, "aa" * 32, store_id=2
        )
        self.crypto._api_post.assert_called_once_with(
            f"transaction/{'aa' * 32}",
            json={"store_id": 2},
        )
        self.assertEqual(result, [["tb1qone", Decimal("0.1"), 3, "receive"]])

    def test_empty_sidecar_response_is_empty_list(self) -> None:
        self.crypto._api_post.return_value = []
        result = UtxoLikeWalletCrypto.getaddrbytx(
            self.crypto, "aa" * 32, store_id=1
        )
        self.assertEqual(result, [])

    @mock.patch("shkeeper.models.StoreWallet")
    def test_merges_outputs_from_all_stores(self, StoreWallet) -> None:
        StoreWallet.query.filter_by.return_value.all.return_value = [
            mock.Mock(store_id=2),
        ]
        self.crypto._api_post.side_effect = [
            [["tb1qa", "1", 1, "receive"]],
            [["tb1qb", "2", 1, "receive"]],
        ]
        result = UtxoLikeWalletCrypto.getaddrbytx(self.crypto, "aa" * 32)
        self.assertEqual(
            [row[0] for row in result],
            ["tb1qa", "tb1qb"],
        )
        self.assertEqual(
            [call.kwargs["json"]["store_id"] for call in self.crypto._api_post.call_args_list],
            [1, 2],
        )

    @mock.patch("shkeeper.models.StoreWallet")
    def test_skips_store_error_and_keeps_other_outputs(self, StoreWallet) -> None:
        StoreWallet.query.filter_by.return_value.all.return_value = [
            mock.Mock(store_id=2),
        ]
        self.crypto._api_post.side_effect = [
            {"status": "error", "error": "wallet not ready"},
            [["tb1qb", "2", 12, "send"]],
        ]
        result = UtxoLikeWalletCrypto.getaddrbytx(self.crypto, "aa" * 32)
        self.assertEqual(result, [["tb1qb", Decimal("2"), 12, "send"]])

    @mock.patch("shkeeper.models.StoreWallet")
    def test_skips_store_exception_and_keeps_other_outputs(self, StoreWallet) -> None:
        StoreWallet.query.filter_by.return_value.all.return_value = [
            mock.Mock(store_id=2),
        ]
        self.crypto._api_post.side_effect = [
            RuntimeError("wallet missing"),
            [["tb1qb", "2", 1, "receive"]],
        ]
        result = UtxoLikeWalletCrypto.getaddrbytx(self.crypto, "aa" * 32)
        self.assertEqual(result, [["tb1qb", Decimal("2"), 1, "receive"]])

    def test_get_confirmations_skips_change_dummy(self) -> None:
        self.crypto._api_post.return_value = [
            ["", 0, 0, "change"],
            ["Daddr", "1.0", 12, "send"],
        ]
        confirms = UtxoLikeWalletCrypto.get_confirmations_by_txid(
            self.crypto, "aa" * 32, store_id=1
        )
        self.assertEqual(confirms, 12)

    def test_get_confirmations_uses_max_send_row(self) -> None:
        self.crypto._api_post.return_value = [
            ["D1", "0.5", 3, "send"],
            ["D2", "0.5", 11, "send"],
        ]
        confirms = UtxoLikeWalletCrypto.get_confirmations_by_txid(
            self.crypto, "aa" * 32, store_id=1
        )
        self.assertEqual(confirms, 11)

    def test_get_confirmations_falls_back_to_dummy(self) -> None:
        self.crypto._api_post.return_value = [["", 0, 7, "change"]]
        confirms = UtxoLikeWalletCrypto.get_confirmations_by_txid(
            self.crypto, "aa" * 32, store_id=1
        )
        self.assertEqual(confirms, 7)


class TestUtxoDumpWallet(unittest.TestCase):
    def setUp(self) -> None:
        self.crypto = _UtxoCrypto()
        self.crypto._api_post = mock.Mock(return_value={"bc1qone": {"wif": "w"}})
        self.crypto._store_payload = lambda store_id=None: (
            UtxoLikeWalletCrypto._store_payload(self.crypto, store_id)
        )

    def test_dumps_only_default_store_when_no_other_wallets(self) -> None:
        with mock.patch("shkeeper.models.StoreWallet") as StoreWallet:
            StoreWallet.query.filter_by.return_value.all.return_value = []
            filename, content = UtxoLikeWalletCrypto.dump_wallet(self.crypto)
        self.crypto._api_post.assert_called_once_with(
            "dump",
            json={"store_id": 1},
            timeout=60,
        )
        self.assertIn("bc1qone", content)
        self.assertTrue(filename.endswith("_DOGE_shkeeper_wallet.json"))

    @mock.patch("shkeeper.models.StoreWallet")
    def test_merges_dumps_from_all_stores(self, StoreWallet) -> None:
        StoreWallet.query.filter_by.return_value.all.return_value = [
            mock.Mock(store_id=2),
        ]
        self.crypto._api_post.side_effect = [
            {"bc1qone": {"wif": "w1"}},
            {"bc1qtwo": {"wif": "w2"}},
        ]
        filename, content = UtxoLikeWalletCrypto.dump_wallet(self.crypto)
        self.assertEqual(
            [call.kwargs["json"]["store_id"] for call in self.crypto._api_post.call_args_list],
            [1, 2],
        )
        self.assertIn("bc1qone", content)
        self.assertIn("bc1qtwo", content)

    def test_dumps_requested_store(self) -> None:
        self.crypto._api_post.return_value = {"bc1qtwo": {"wif": "w"}}
        filename, content = UtxoLikeWalletCrypto.dump_wallet(self.crypto, store_id=2)
        self.crypto._api_post.assert_called_once_with(
            "dump",
            json={"store_id": 2},
            timeout=60,
        )
        self.assertIn("bc1qtwo", content)
