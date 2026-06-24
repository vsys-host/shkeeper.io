import traceback
from functools import wraps
from os import environ

from flask import current_app as app, request

from shkeeper.modules.classes.crypto import Crypto


def resolve_available_crypto(crypto_name):
    try:
        crypto = Crypto.instances[crypto_name]
    except KeyError:
        return None, {
            "status": "error",
            "message": f"{crypto_name} payment gateway is unavailable",
        }
    if not crypto.wallet.enabled:
        return None, {
            "status": "error",
            "message": f"{crypto_name} payment gateway is unavailable",
        }
    if (
        app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
        and crypto.getstatus() != "Synced"
    ):
        return None, {
            "status": "error",
            "message": f"{crypto_name} payment gateway is unavailable because of lagging",
        }
    return crypto, None


def api_error_response(exc, log_message, *, message=None, status_code=200, log=True):
    if log:
        app.logger.exception(log_message)
    response = {
        "status": "error",
        "message": message if message is not None else str(exc),
        "traceback": traceback.format_exc(),
    }
    if status_code == 200:
        return response
    return response, status_code


def verify_backend_key():
    if "X-Shkeeper-Backend-Key" not in request.headers:
        app.logger.warning("No backend key provided")
        return {"status": "error", "message": "No backend key provided"}, 403

    bkey = environ.get("SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
    if request.headers["X-Shkeeper-Backend-Key"] != bkey:
        app.logger.warning("Wrong backend key")
        return {"status": "error", "message": "Wrong backend key"}, 403

    return None


def handle_request_error(log_message="Request error"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return api_error_response(e, log_message, status_code=500)

        return wrapper

    return decorator
