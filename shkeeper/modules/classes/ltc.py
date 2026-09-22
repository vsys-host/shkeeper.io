from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto


class Ltc(UtxoLikeWalletCrypto):
    env_prefix = "LTC"
    default_host = "litecoin-shkeeper"
