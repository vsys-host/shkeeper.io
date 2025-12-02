from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from shkeeper.services.crypto_cache import get_available_cryptos
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.utils import format_decimal
from shkeeper.models import ExchangeRate
from flask import current_app

def _build_balance(crypto_name: str, logger, app):
    with app.app_context():
        crypto = Crypto.instances.get(crypto_name)
        if not crypto:
            return None
        fiat = "USD"
        try:
            rate = ExchangeRate.get(fiat, crypto_name).get_rate()
            crypto_amount = Decimal(crypto.balance() or 0)
            amount_fiat = crypto_amount * Decimal(rate)
            server_status = crypto.getstatus()
        except Exception as e:
            logger.exception(f"_build_balance exception for {crypto_name}")
            return None
        return {
            "name": crypto.crypto,
            "display_name": crypto.display_name,
            "amount_crypto": format_decimal(crypto_amount),
            "rate": format_decimal(rate),
            "fiat": fiat,
            "amount_fiat": format_decimal(amount_fiat),
            "server_status": server_status,
        }

def get_balances(includes: list[str] | None):
    app = current_app._get_current_object()
    logger = app.logger
    data = get_available_cryptos()
    available_coins = data["filtered"]
    if includes:
        includes = [c.strip().upper() for c in includes if c.strip()]
        target = [c for c in includes if c in available_coins]
        if not target:
            return None, "No valid cryptos requested"
    else:
        target = sorted(available_coins)
    with ThreadPoolExecutor() as executor:
        results = list(
            executor.map(lambda c: _build_balance(c, logger, app), target)
        )
    balances = [x for x in results if x]
    return balances, None
