from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto


class Doge(UtxoLikeWalletCrypto):
    env_prefix = "DOGE"
    default_host = "dogecoin-shkeeper"
