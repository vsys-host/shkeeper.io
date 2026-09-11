from shkeeper.modules.classes.utxo_http_wallet import UtxoHttpWallet


class Ltc(UtxoHttpWallet):
    env_prefix = "LTC"
    default_host = "litecoin-shkeeper"
    network_currency = "LTC"
