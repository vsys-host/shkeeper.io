from __future__ import annotations
import hashlib
import hmac
import importlib.util
import unittest
from pathlib import Path


def _load_webhook_hmac_from_path():
    root = Path(__file__).resolve().parents[1]
    path = root / "shkeeper" / "services" / "webhook_hmac.py"
    spec = importlib.util.spec_from_file_location(
        "shkeeper_services_webhook_hmac_testonly", path
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    from shkeeper.services import webhook_hmac as wh
except Exception:  # noqa: BLE001 — shkeeper/__init__ pulls Flask/DB; tests only need this module
    wh = _load_webhook_hmac_from_path()


class TestCompactJsonBytes(unittest.TestCase):
    def test_sorts_keys_deterministically(self) -> None:
        a = wh.compact_json_bytes({"z": 1, "a": 2})
        b = wh.compact_json_bytes({"a": 2, "z": 1})
        self.assertEqual(a, b)
        self.assertEqual(a, b'{"a":2,"z":1}')

    def test_separators_no_spaces(self) -> None:
        out = wh.compact_json_bytes({"x": [1, 2, 3]})
        self.assertEqual(out, b'{"x":[1,2,3]}')

    def test_unicode_not_ascii_escaped(self) -> None:
        out = wh.compact_json_bytes({"msg": "київ"})
        self.assertIn("київ".encode("utf-8"), out)
        self.assertNotIn(b"\\u", out)


class TestHmacV1(unittest.TestCase):
    def test_known_vector_matches_manual_hmac(self) -> None:
        secret = "test-api-key"
        body = b'{"a":1}'
        ts = 1_700_000_000
        key = secret.encode("utf-8")
        msg = f"{ts}.".encode("ascii") + body
        expected = hmac.new(key, msg, hashlib.sha256).hexdigest()
        self.assertEqual(wh._hmac_v1(secret, body, ts), expected)
        self.assertEqual(len(expected), 64)


class TestShkeeperWebhookAuthHeaders(unittest.TestCase):
    def test_headers_match_hmac_and_timestamp(self) -> None:
        secret = "secret"
        body = b"{}"
        ts = 42
        headers = wh.shkeeper_webhook_auth_headers(secret, body, timestamp=ts)
        self.assertEqual(headers[wh.WEBHOOK_TIMESTAMP_HEADER], "42")
        self.assertEqual(
            headers[wh.WEBHOOK_SIGNATURE_HEADER],
            wh._hmac_v1(secret, body, ts),
        )


class TestVerifyWebhook(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "my-key"
        self.body = wh.compact_json_bytes({"paid": True, "id": 1})
        self.ts = 1_700_000_100
        self.good_sig = wh._hmac_v1(self.secret, self.body, self.ts)

    def test_accepts_valid_signature_at_now(self) -> None:
        self.assertTrue(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex=self.good_sig,
                now=self.ts,
            )
        )

    def test_accepts_within_max_age(self) -> None:
        self.assertTrue(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex=self.good_sig,
                now=self.ts + 299,
                max_age_sec=300,
            )
        )

    def test_rejects_expired_timestamp(self) -> None:
        self.assertFalse(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex=self.good_sig,
                now=self.ts + 301,
                max_age_sec=300,
            )
        )

    def test_rejects_wrong_signature(self) -> None:
        bad = "a" * 64
        self.assertFalse(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex=bad,
                now=self.ts,
            )
        )

    def test_rejects_tampered_body(self) -> None:
        other_body = wh.compact_json_bytes({"paid": False, "id": 1})
        self.assertFalse(
            wh.verify_webhook(
                self.secret,
                other_body,
                timestamp=self.ts,
                signature_hex=self.good_sig,
                now=self.ts,
            )
        )

    def test_rejects_short_or_long_hex(self) -> None:
        self.assertFalse(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex="ab" * 31,
                now=self.ts,
            )
        )
        self.assertFalse(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex="ab" * 33,
                now=self.ts,
            )
        )

    def test_strips_and_casefolds_signature(self) -> None:
        spaced = "  " + self.good_sig.upper() + "  "
        self.assertTrue(
            wh.verify_webhook(
                self.secret,
                self.body,
                timestamp=self.ts,
                signature_hex=spaced,
                now=self.ts,
            )
        )

    def test_round_trip_with_auth_headers(self) -> None:
        body = wh.compact_json_bytes({"x": 1})
        ts = 99
        hdrs = wh.shkeeper_webhook_auth_headers("k", body, timestamp=ts)
        self.assertTrue(
            wh.verify_webhook(
                "k",
                body,
                timestamp=int(hdrs[wh.WEBHOOK_TIMESTAMP_HEADER]),
                signature_hex=hdrs[wh.WEBHOOK_SIGNATURE_HEADER],
                now=ts,
            )
        )


if __name__ == "__main__":
    unittest.main()
