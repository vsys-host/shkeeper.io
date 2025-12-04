from concurrent.futures import ThreadPoolExecutor
from operator import itemgetter
from flask import current_app as app
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.services.cache_service import cache

CACHE_TTL = 60  # seconds

def _fetch_available_cryptos():
    disable_on_lags = app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
    cryptos = [c for c in Crypto.instances.values() if c.wallet.enabled]
    def check_status(crypto):
        return crypto, crypto.getstatus()

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(check_status, cryptos))

    filtered = []
    crypto_list = []

    for crypto, status in results:
        if status == "Offline":
            continue
        if disable_on_lags and status != "Synced":
            continue

        filtered.append(crypto.crypto)
        crypto_list.append({
            "name": crypto.crypto,
            "display_name": crypto.display_name
        })
    return {
        "filtered": sorted(filtered),
        "crypto_list": sorted(crypto_list, key=itemgetter("name")),
    }

def get_available_cryptos():
    return cache.remember("available_cryptos", CACHE_TTL, _fetch_available_cryptos)