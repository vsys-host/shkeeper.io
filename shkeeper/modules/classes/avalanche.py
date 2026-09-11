from shkeeper.modules.classes.ethereum import Ethereum


class Avalanche(Ethereum):
    host_env_prefix = "AVALANCHE"
    creds_env_prefix = "AVALANCHE"
    default_host = "avalanche-shkeeper"
    network_currency = "AVAX"
    block_interval = 2
