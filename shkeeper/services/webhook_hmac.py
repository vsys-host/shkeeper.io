from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

WEBHOOK_SIGNATURE_HEADER = "X-Shkeeper-Signature"
WEBHOOK_TIMESTAMP_HEADER = "X-Shkeeper-Timestamp"


def compact_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def _hmac_v1(secret: str, body: bytes, ts: int) -> str:
    key = secret.encode("utf-8")
    msg = f"{ts}.".encode("ascii") + body
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def shkeeper_webhook_auth_headers(
    secret: str, body: bytes, timestamp: int | None = None
) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    digest = _hmac_v1(secret, body, ts)
    return {
        WEBHOOK_TIMESTAMP_HEADER: str(ts),
        WEBHOOK_SIGNATURE_HEADER: digest,
    }


def verify_webhook(
    secret: str,
    body: bytes,
    *,
    timestamp: int,
    signature_hex: str,
    max_age_sec: int = 300,
    now: int | None = None,
) -> bool:
    sig = signature_hex.strip().lower()
    if len(sig) != 64:
        return False
    clock = int(time.time()) if now is None else int(now)
    if abs(clock - int(timestamp)) > max_age_sec:
        return False
    expected = _hmac_v1(secret, body, int(timestamp))
    return hmac.compare_digest(expected, sig)
