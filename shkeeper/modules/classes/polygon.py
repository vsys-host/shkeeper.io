from shkeeper.modules.classes.ethereum import Ethereum


class Polygon(Ethereum):
    host_env_prefix = "POLYGON"
    creds_env_prefix = "POLYGON"
    default_host = "polygon-shkeeper"
    network_currency = "MATIC"
    block_interval = 2
