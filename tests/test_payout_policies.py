"""Unit tests for native-coin autopayout routing (dual-path mkpayout).

Guards the regression fixed in btc.py/ltc.py/doge.py: the old code did a
unit-confused `fee >= amount` check and returned an *error string* (crashing
do_payout). The fix routes a full payout (amount >= balance) to the node-side
/sweep-payout, and a partial/reserve payout (amount < balance) to the existing
/payout (where the retained reserve covers the fee). No client-side fee math.

Importing `shkeeper` pulls Flask/DB, so we stub the import deps and exercise the
real mkpayout method on instances built with __new__ (bypassing the base
__init__). Run: python3 -m unittest tests.test_payout_policies
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COINS = ("btc", "ltc", "doge")
NETWORK_CCY = {"btc": "BTC", "ltc": "LTC", "doge": "DOGE"}


def _install_stubs() -> mock.MagicMock:
    """Inject minimal stand-ins so the coin modules import without the app."""
    fake_requests = mock.MagicMock(name="shkeeper.requests")

    shk = types.ModuleType("shkeeper")
    shk.__path__ = []  # mark as package
    shk.requests = fake_requests
    sys.modules["shkeeper"] = shk

    for name in ("shkeeper.modules", "shkeeper.modules.classes"):
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m

    crypto_mod = types.ModuleType("shkeeper.modules.classes.crypto")

    class Crypto:  # minimal base; real one pulls the world
        instances: dict = {}

    crypto_mod.Crypto = Crypto
    sys.modules["shkeeper.modules.classes.crypto"] = crypto_mod

    flask_mod = types.ModuleType("flask")
    flask_mod.current_app = types.SimpleNamespace(
        logger=types.SimpleNamespace(
            warning=lambda *a, **k: None, info=lambda *a, **k: None
        )
    )
    sys.modules["flask"] = flask_mod
    return fake_requests


def _load_coin(coin: str):
    path = ROOT / "shkeeper" / "modules" / "classes" / f"{coin}.py"
    spec = importlib.util.spec_from_file_location(f"_test_{coin}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_instance(coin: str, balance: Decimal):
    fake_requests = _install_stubs()
    mod = _load_coin(coin)
    cls = getattr(mod, coin.capitalize())  # Btc / Ltc / Doge
    inst = cls.__new__(cls)
    inst.crypto = NETWORK_CCY[coin]
    inst.gethost = lambda: "sidecar:6000"
    inst.get_auth_creds = lambda: ("shkeeper", "shkeeper")
    inst.balance = lambda: balance
    # requests.post(...).json(parse_float=...) -> a successful task dict
    fake_requests.post.return_value.json.return_value = {"task_id": "T-OK"}
    return cls, inst, fake_requests


class TestDualPathRouting(unittest.TestCase):
    def test_full_payout_routes_to_sweep(self) -> None:
        for coin in COINS:
            with self.subTest(coin=coin):
                cls, inst, req = _make_instance(coin, balance=Decimal("0.5"))
                # full payout: amount == balance (DISABLE reserve policy)
                res = cls.mkpayout(inst, "ADDR", Decimal("0.5"), 0,
                                   subtract_fee_from_amount=True)
                url = req.post.call_args[0][0]
                self.assertIn("/sweep-payout/ADDR", url)
                self.assertNotIn("/payout/", url)  # not the standard payout route
                self.assertEqual(res, {"task_id": "T-OK"})
                self.assertIsInstance(res, dict)  # never an error string

    def test_partial_payout_routes_to_standard_payout(self) -> None:
        for coin in COINS:
            with self.subTest(coin=coin):
                cls, inst, req = _make_instance(coin, balance=Decimal("1.0"))
                # reserve kept: amount < balance (AMOUNT/PERCENT policy)
                res = cls.mkpayout(inst, "ADDR", Decimal("0.4"), "150",
                                   subtract_fee_from_amount=True)
                url = req.post.call_args[0][0]
                self.assertIn("/payout/ADDR/", url)
                self.assertNotIn("/sweep-payout/", url)
                self.assertEqual(res, {"task_id": "T-OK"})

    def test_returns_dict_not_error_string(self) -> None:
        # The regression returned an f-string on every native autopayout.
        for coin in COINS:
            with self.subTest(coin=coin):
                cls, inst, _ = _make_instance(coin, balance=Decimal("0.2"))
                res = cls.mkpayout(inst, "ADDR", Decimal("0.2"), 0,
                                   subtract_fee_from_amount=True)
                self.assertNotIsInstance(res, str)


class TestRegressionGuardStatic(unittest.TestCase):
    """Fail loudly if the buggy fee-vs-amount block ever reappears."""

    def test_no_fee_ge_amount_block(self) -> None:
        for coin in COINS:
            with self.subTest(coin=coin):
                src = (ROOT / "shkeeper" / "modules" / "classes" / f"{coin}.py").read_text()
                self.assertNotIn("if fee >= amount", src)
                self.assertNotIn("not enought", src)  # the old error string
                self.assertIn("/sweep-payout/", src)  # dual-path present


if __name__ == "__main__":
    unittest.main()
