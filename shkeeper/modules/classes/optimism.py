from shkeeper.modules.classes.ethereum import Ethereum


class Optimism(Ethereum):
    host_env_prefix = "OPTIMISM"
    creds_env_prefix = "OP"
    default_host = "optimism-shkeeper"
    network_currency = "OPETH"
    block_interval = 1
    sync_lag_multiplier = 180
