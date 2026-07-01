from shkeeper.modules.classes.ethereum import Ethereum


class Arbitrum(Ethereum):
    host_env_prefix = "ARBITRUM"
    creds_env_prefix = "ARB"
    default_host = "arbitrum-shkeeper"
    network_currency = "ARBETH"
    block_interval = 2
