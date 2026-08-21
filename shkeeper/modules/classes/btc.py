from shkeeper.modules.classes.utxo_http_wallet import UtxoHttpWallet


class Btc(UtxoHttpWallet):
    env_prefix = "BTC"
    default_host = "bitcoin-shkeeper"
    network_currency = "BTC"
    log_tx_response = True
