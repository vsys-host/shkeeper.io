from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto


class Btc(UtxoLikeWalletCrypto):
    env_prefix = "BTC"
    default_host = "bitcoin-shkeeper"
