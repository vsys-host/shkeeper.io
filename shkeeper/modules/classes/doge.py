from shkeeper.modules.classes.shkeeper_wallet_crypto import UtxoLikeWalletCrypto


class Doge(UtxoLikeWalletCrypto):
    env_prefix = "DOGE"
    default_host = "dogecoin-shkeeper"
