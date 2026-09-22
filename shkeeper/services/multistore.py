MULTISTORE_SUPPORTED = frozenset(
    {
        # Ethereum
        "ETH",
        "ETH-USDT",
        "ETH-USDC",
        "ETH-PYUSD",
        "ETH-DAI",
        # Arbitrum
        "ARBETH",
        "ARB-USDC",
        "ARB-PYUSD",
        "ARB-TOKEN",
        # Optimism
        "OPETH",
        "OP-USDT",
        "OP-USDC",
        "OP-TOKEN",
        # BNB
        "BNB",
        "BNB-USDT",
        "BNB-USDC",
        # Polygon
        "MATIC",
        "POLYGON-USDT",
        "POLYGON-USDC",
        # Avalanche
        "AVAX",
        "AVALANCHE-USDT",
        "AVALANCHE-USDC",
        # Tron
        "TRX",
        "USDT",
        "USDC",
        # Bitcoin-like
        "BTC",
        "LTC",
        "DOGE",
    }
)

DEFAULT_STORE_NAME = "Default"


def crypto_supports_multistore(crypto_name: str) -> bool:
    return crypto_name in MULTISTORE_SUPPORTED


def autopayout_store_kwargs(crypto_name: str) -> dict:
    """Autopayout uses the default admin store, and only on multistore coins."""
    if not crypto_supports_multistore(crypto_name):
        return {}
    from shkeeper.services.store_service import DEFAULT_ADMIN_STORE_ID

    return {"store_id": DEFAULT_ADMIN_STORE_ID}


def is_multistore_backend(crypto) -> bool:
    if crypto is None:
        return False
    from shkeeper.modules.classes.ethereum import Ethereum
    from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto
    from shkeeper.modules.classes.tron_token import TronToken

    return isinstance(crypto, (Ethereum, TronToken, UtxoLikeWalletCrypto))


def uses_fee_deposit_account(crypto) -> bool:
    """ETH-like and Tron have an FDA; BTC/LTC/DOGE do not."""
    if crypto is None:
        return False
    from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto

    return is_multistore_backend(crypto) and not isinstance(
        crypto, UtxoLikeWalletCrypto
    )


def store_wallet_is_ready(sw, crypto=None) -> bool:
    """True when the store can create addresses / payout for this crypto."""
    if not sw:
        return False
    from shkeeper.models import StoreWalletStatus

    if sw.status != StoreWalletStatus.READY:
        return False
    if crypto is None:
        from shkeeper.modules.classes.crypto import Crypto

        crypto = Crypto.instances.get(getattr(sw, "crypto", None))
    if crypto is None:
        crypto_name = getattr(sw, "crypto", None)
        if crypto_name in ("BTC", "LTC", "DOGE"):
            return True
        return bool(getattr(sw, "fda_address", None))
    if uses_fee_deposit_account(crypto):
        return bool(sw.fda_address)
    return True


def filter_multistore_cryptos(crypto_names):
    return [name for name in crypto_names if crypto_supports_multistore(name)]


def autopayout_allowed(user=None):
    from flask import has_request_context

    from shkeeper.services.tenancy import is_admin_user

    if user is not None:
        return is_admin_user(user)
    if has_request_context():
        return is_admin_user()
    return True
