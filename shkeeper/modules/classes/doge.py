from shkeeper.modules.classes.utxo_http_wallet import UtxoHttpWallet


class Doge(UtxoHttpWallet):
    env_prefix = "DOGE"
    default_host = "dogecoin-shkeeper"
    network_currency = "DOGE"
