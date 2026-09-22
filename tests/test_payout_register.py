from __future__ import annotations

import unittest
from decimal import Decimal
from unittest import mock

from flask import Flask

from shkeeper.models import Payout, PayoutStatus


class _AppContextTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._flask_app = Flask(__name__)
        self._app_ctx = self._flask_app.app_context()
        self._app_ctx.push()
        self.addCleanup(self._app_ctx.pop)


class TestFormatMkpayoutError(unittest.TestCase):
    def test_none_returns_none(self) -> None:
        self.assertIsNone(Payout._format_mkpayout_error(None))

    def test_string_returned_as_is(self) -> None:
        self.assertEqual(Payout._format_mkpayout_error("boom"), "boom")

    def test_dict_with_message_uses_message(self) -> None:
        self.assertEqual(
            Payout._format_mkpayout_error({"message": "not enough funds", "code": 5}),
            "not enough funds",
        )

    def test_dict_without_message_stringifies(self) -> None:
        err = {"code": 5}
        self.assertEqual(Payout._format_mkpayout_error(err), str(err))

    def test_dict_with_empty_message_falls_back_to_str(self) -> None:
        err = {"message": "", "code": 5}
        self.assertEqual(Payout._format_mkpayout_error(err), str(err))

    def test_non_str_non_dict_stringifies(self) -> None:
        self.assertEqual(Payout._format_mkpayout_error(500), "500")


class TestAddFailed(_AppContextTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db_patcher = mock.patch("shkeeper.models.db")
        self.db = self.db_patcher.start()
        self.addCleanup(self.db_patcher.stop)

    def test_creates_failed_record_and_persists(self) -> None:
        p = Payout.add_failed(
            dest="addr1",
            amount=Decimal("1.5"),
            crypto="BTC",
            error="node offline",
            callback_url="https://cb.example/hook",
            external_id="ext-1",
        )
        self.assertEqual(p.dest_addr, "addr1")
        self.assertEqual(p.amount, Decimal("1.5"))
        self.assertEqual(p.crypto, "BTC")
        self.assertEqual(p.status, PayoutStatus.FAIL)
        self.assertEqual(p.success, "No")
        self.assertEqual(p.error, "node offline")
        self.assertEqual(p.callback_url, "https://cb.example/hook")
        self.assertEqual(p.external_id, "ext-1")
        self.db.session.add.assert_called_once_with(p)
        self.db.session.commit.assert_called_once()

    def test_dict_error_is_formatted(self) -> None:
        p = Payout.add_failed(
            dest="addr1",
            amount=Decimal("1"),
            crypto="LTC",
            error={"message": "insufficient funds"},
        )
        self.assertEqual(p.error, "insufficient funds")

    def test_empty_external_id_normalized_to_none(self) -> None:
        p = Payout.add_failed(dest="a", amount=Decimal("1"), crypto="BTC", external_id="")
        self.assertIsNone(p.external_id)

    def test_missing_error_is_none(self) -> None:
        p = Payout.add_failed(dest="a", amount=Decimal("1"), crypto="BTC")
        self.assertIsNone(p.error)


class TestRegisterFromMkpayout(_AppContextTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_patcher = mock.patch.object(Payout, "add")
        self.add_failed_patcher = mock.patch.object(Payout, "add_failed")
        self.add = self.add_patcher.start()
        self.add_failed = self.add_failed_patcher.start()
        self.addCleanup(self.add_patcher.stop)
        self.addCleanup(self.add_failed_patcher.stop)

        self.payout = {
            "dest": "addr1",
            "amount": Decimal("2"),
            "callback_url": "https://cb.example/hook",
        }

    def test_dict_with_error_routes_to_add_failed(self) -> None:
        res = {"error": "boom"}
        out = Payout.register_from_mkpayout(res, self.payout, "BTC", external_id="ext-1")

        self.add_failed.assert_called_once_with(
            "addr1",
            Decimal("2"),
            "BTC",
            error="boom",
            callback_url="https://cb.example/hook",
            external_id="ext-1",
        )
        self.add.assert_not_called()
        self.assertIs(out, self.add_failed.return_value)

    def test_dict_with_task_id_only_routes_to_add(self) -> None:
        res = {"task_id": "task-123"}
        out = Payout.register_from_mkpayout(res, self.payout, "BTC", external_id="ext-1")

        self.add.assert_called_once_with(
            {
                "dest": "addr1",
                "amount": Decimal("2"),
                "callback_url": "https://cb.example/hook",
                "txids": [],
            },
            "BTC",
            task_id="task-123",
            external_id="ext-1",
            store_id=None,
        )
        self.add_failed.assert_not_called()
        self.assertIs(out, self.add.return_value)

    def test_dict_result_list_kept_as_txids(self) -> None:
        res = {"task_id": "t1", "result": ["tx1", "tx2"]}
        Payout.register_from_mkpayout(res, self.payout, "BTC")

        payout_arg = self.add.call_args.args[0]
        self.assertEqual(payout_arg["txids"], ["tx1", "tx2"])
        self.assertEqual(self.add.call_args.kwargs["task_id"], "t1")

    def test_dict_result_scalar_wrapped_in_list(self) -> None:
        res = {"result": "tx-single"}
        Payout.register_from_mkpayout(res, self.payout, "BTC")

        payout_arg = self.add.call_args.args[0]
        self.assertEqual(payout_arg["txids"], ["tx-single"])
        self.assertIsNone(self.add.call_args.kwargs["task_id"])

    def test_dict_result_only_routes_to_add(self) -> None:
        res = {"result": ["tx1"]}
        out = Payout.register_from_mkpayout(res, self.payout, "BTC")
        self.add.assert_called_once()
        self.assertIs(out, self.add.return_value)

    def test_empty_dict_creates_no_record(self) -> None:
        out = Payout.register_from_mkpayout({}, self.payout, "BTC")
        self.assertIsNone(out)
        self.add.assert_not_called()
        self.add_failed.assert_not_called()

    def test_dict_without_relevant_keys_creates_no_record(self) -> None:
        out = Payout.register_from_mkpayout({"foo": "bar"}, self.payout, "BTC")
        self.assertIsNone(out)
        self.add.assert_not_called()
        self.add_failed.assert_not_called()

    def test_string_response_routes_to_add_failed(self) -> None:
        out = Payout.register_from_mkpayout("some error", self.payout, "BTC", external_id="ext-9")

        self.add_failed.assert_called_once_with(
            "addr1",
            Decimal("2"),
            "BTC",
            error="some error",
            callback_url="https://cb.example/hook",
            external_id="ext-9",
        )
        self.add.assert_not_called()
        self.assertIs(out, self.add_failed.return_value)

    def test_none_response_creates_no_record(self) -> None:
        out = Payout.register_from_mkpayout(None, self.payout, "BTC")
        self.assertIsNone(out)
        self.add.assert_not_called()
        self.add_failed.assert_not_called()

    def test_unexpected_type_creates_no_record(self) -> None:
        out = Payout.register_from_mkpayout(["tx1"], self.payout, "BTC")
        self.assertIsNone(out)
        self.add.assert_not_called()
        self.add_failed.assert_not_called()

    def test_missing_callback_url_defaults_to_none(self) -> None:
        payout = {"dest": "addr1", "amount": Decimal("2")}
        Payout.register_from_mkpayout({"task_id": "t1"}, payout, "BTC")
        payout_arg = self.add.call_args.args[0]
        self.assertIsNone(payout_arg["callback_url"])


class TestWalletDoPayout(_AppContextTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db_patcher = mock.patch("shkeeper.models.db")
        self.crypto_instances_patcher = mock.patch("shkeeper.models.Crypto.instances", {})
        self.register_patcher = mock.patch.object(Payout, "register_from_mkpayout")
        self.db = self.db_patcher.start()
        self.crypto_instances = self.crypto_instances_patcher.start()
        self.register = self.register_patcher.start()
        self.addCleanup(self.db_patcher.stop)
        self.addCleanup(self.crypto_instances_patcher.stop)
        self.addCleanup(self.register_patcher.stop)

    def _make_wallet(self) -> "Wallet":
        from shkeeper.models import Wallet

        wallet = Wallet()
        wallet.crypto = "ETH"
        wallet.payout = True
        wallet.pdest = "0xdest"
        wallet.pfee = "0.001"
        return wallet

    def test_amount_policy_records_should_payout_amount(self) -> None:
        from shkeeper.models import PayoutReservePolicy

        wallet = self._make_wallet()
        crypto = mock.Mock()
        crypto.balance.return_value = Decimal("10")
        crypto.wallet = mock.Mock()
        crypto.wallet.prespolicy = PayoutReservePolicy.AMOUNT
        crypto.wallet.presamount = "3"
        crypto.mkpayout.return_value = {"result": "0xtx"}
        self.crypto_instances["ETH"] = crypto

        wallet.do_payout()

        crypto.balance.assert_called_with(store_id=1)
        crypto.mkpayout.assert_called_once_with(
            "0xdest",
            Decimal("7"),
            "0.001",
            subtract_fee_from_amount=True,
            store_id=1,
        )
        self.assertEqual(self.register.call_args.args[1]["amount"], Decimal("7"))
        self.assertEqual(self.register.call_args.kwargs.get("store_id"), 1)

    def test_percent_policy_records_should_payout_amount(self) -> None:
        from shkeeper.models import PayoutReservePolicy

        wallet = self._make_wallet()
        crypto = mock.Mock()
        crypto.balance.return_value = Decimal("10")
        crypto.wallet = mock.Mock()
        crypto.wallet.prespolicy = PayoutReservePolicy.PERCENT
        crypto.wallet.presamount = "20"
        crypto.mkpayout.return_value = {"result": "0xtx"}
        self.crypto_instances["ETH"] = crypto

        wallet.do_payout()

        crypto.balance.assert_called_with(store_id=1)
        crypto.mkpayout.assert_called_once_with(
            "0xdest",
            Decimal("8"),
            "0.001",
            subtract_fee_from_amount=True,
            store_id=1,
        )
        self.assertEqual(self.register.call_args.args[1]["amount"], Decimal("8"))
        self.assertEqual(self.register.call_args.kwargs.get("store_id"), 1)


class TestUpdateFromNotify(_AppContextTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db_patcher = mock.patch("shkeeper.models.db")
        self.db = self.db_patcher.start()
        self.addCleanup(self.db_patcher.stop)

    def test_store_fee_and_merchant_share_one_btc_txid(self) -> None:
        fee = mock.Mock()
        fee.id = 11
        fee.task_id = "task-1"
        fee.dest_addr = "tb1q9jrhnfe5neu720h2v8xjeu4gged0j37pem2x0x"
        fee.transactions = []
        merchant = mock.Mock()
        merchant.id = 12
        merchant.task_id = "task-1"
        merchant.dest_addr = "tb1qxfsnwjyfucv4scm3eql0gm68exxp2zgd6ckwc9"
        merchant.transactions = []
        fee.created_at = "2026-09-14 11:50:00"
        merchant.created_at = "2026-09-14 11:50:00"
        old_fee = mock.Mock()
        old_fee.id = 1
        old_fee.task_id = "task-old"
        old_fee.dest_addr = fee.dest_addr
        old_fee.created_at = "2026-09-14 09:24:00"
        old_fee.transactions = []
        old_merchant = mock.Mock()
        old_merchant.id = 2
        old_merchant.task_id = "task-old"
        old_merchant.dest_addr = merchant.dest_addr
        old_merchant.created_at = "2026-09-14 09:24:00"
        old_merchant.transactions = []
        txid = "14acab8acae85d8f759ce11249605eaebc9e9fb264e67abc1af12679ea0e58b1"
        query = mock.Mock()
        query.filter.return_value.all.return_value = [
            old_fee,
            old_merchant,
            fee,
            merchant,
        ]
        query.filter_by.return_value.all.return_value = [fee, merchant]
        Payout.query = query
        try:
            Payout.update_from_notify(
                "BTC",
                [
                    {
                        "dest": fee.dest_addr,
                        "amount": 5.21e-06,
                        "status": "success",
                        "txids": [txid],
                    },
                    {
                        "dest": merchant.dest_addr,
                        "amount": 4.693e-05,
                        "status": "success",
                        "txids": [txid],
                    },
                ],
            )
        finally:
            delattr(Payout, "query")

        added = [c.args[0] for c in self.db.session.add.call_args_list]
        self.assertEqual({row.payout_id for row in added}, {11, 12})
        self.assertEqual({row.txid for row in added}, {txid})
        self.db.session.commit.assert_called()

    def test_attaches_newest_payout_per_destination(self) -> None:
        fee = mock.Mock()
        fee.id = 21
        fee.task_id = None
        fee.dest_addr = "tb1qfee"
        fee.created_at = "2026-09-21 12:00:00"
        fee.transactions = []
        merchant = mock.Mock()
        merchant.id = 22
        merchant.task_id = None
        merchant.dest_addr = "tb1qmerchant"
        merchant.created_at = "2026-09-21 12:00:02"
        merchant.transactions = []
        old_fee = mock.Mock()
        old_fee.id = 1
        old_fee.task_id = None
        old_fee.dest_addr = fee.dest_addr
        old_fee.created_at = "2026-09-21 10:00:00"
        old_fee.transactions = []
        txid = "aa" * 32
        query = mock.Mock()
        query.filter.return_value.all.return_value = [old_fee, fee, merchant]
        Payout.query = query
        try:
            Payout.update_from_notify(
                "BTC",
                [
                    {
                        "dest": fee.dest_addr,
                        "status": "success",
                        "txids": [txid],
                    },
                    {
                        "dest": merchant.dest_addr,
                        "status": "success",
                        "txids": [txid],
                    },
                ],
            )
        finally:
            delattr(Payout, "query")

        added = [c.args[0] for c in self.db.session.add.call_args_list]
        self.assertEqual({row.payout_id for row in added}, {21, 22})
        self.assertEqual({row.txid for row in added}, {txid})


if __name__ == "__main__":
    unittest.main()
