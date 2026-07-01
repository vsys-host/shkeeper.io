from shkeeper.modules.classes.ethereum import Ethereum


class Solana(Ethereum):
    host_env_prefix = "SOLANA"
    creds_env_prefix = "SOLANA"
    default_host = "solana-shkeeper"
    network_currency = "SOL"
    block_interval = 1
    sync_lag_multiplier = 100
