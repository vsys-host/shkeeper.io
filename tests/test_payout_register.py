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


if __name__ == "__main__":
    unittest.main()
