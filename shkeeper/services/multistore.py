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
    }
)

DEFAULT_STORE_NAME = "Default"


def crypto_supports_multistore(crypto_name: str) -> bool:
    return crypto_name in MULTISTORE_SUPPORTED


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
