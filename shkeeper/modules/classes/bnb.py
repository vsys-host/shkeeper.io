from shkeeper.modules.classes.ethereum import Ethereum


class Bnb(Ethereum):
    host_env_prefix = "BNB"
    creds_env_prefix = "BNB"
    default_host = "bnb-shkeeper"
    network_currency = "BNB"
