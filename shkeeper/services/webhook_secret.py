from __future__ import annotations

import secrets

from shkeeper import db
from shkeeper.models import Setting
from shkeeper.services.webhook_hmac import (
    resolve_webhook_signing_secret,
    shkeeper_webhook_auth_headers,
)

WEBHOOK_SECRET_SETTING_NAME = "WebhookHMACSecret"
MIN_WEBHOOK_SECRET_LENGTH = 32
MAX_WEBHOOK_SECRET_LENGTH = 255


def get_configured_webhook_secret() -> str | None:
    """Return the global webhook secret without exposing it through an API."""
    setting = Setting.query.get(WEBHOOK_SECRET_SETTING_NAME)
    return setting.value if setting and setting.value else None


def set_configured_webhook_secret(secret: str) -> None:
    """Store the global webhook secret in the existing settings table."""
    setting = Setting.query.get(WEBHOOK_SECRET_SETTING_NAME)
    if setting is None:
        setting = Setting(name=WEBHOOK_SECRET_SETTING_NAME)
        db.session.add(setting)
    setting.value = secret


def clear_configured_webhook_secret() -> None:
    """Remove the global webhook secret and restore API-key fallback."""
    setting = Setting.query.get(WEBHOOK_SECRET_SETTING_NAME)
    if setting is not None:
        db.session.delete(setting)


def generate_webhook_secret() -> str:
    """Generate a 256-bit candidate secret without activating it."""
    return secrets.token_urlsafe(32)


def build_webhook_auth_headers(
    api_key: str | None,
    body: bytes,
    *,
    include_legacy_api_key: bool = False,
) -> dict[str, str] | None:
    """Build signature headers and expose the API key only in fallback mode."""
    dedicated_secret = get_configured_webhook_secret()
    signing_secret = resolve_webhook_signing_secret(dedicated_secret, api_key)
    if not signing_secret:
        return None

    headers = shkeeper_webhook_auth_headers(signing_secret, body)
    if include_legacy_api_key and not dedicated_secret and api_key:
        headers["X-Shkeeper-Api-Key"] = api_key
    return headers
