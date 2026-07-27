from shkeeper.modules.classes.shkeeper_wallet_crypto import UtxoLikeWalletCrypto


class Ltc(UtxoLikeWalletCrypto):
    env_prefix = "LTC"
    default_host = "litecoin-shkeeper"
