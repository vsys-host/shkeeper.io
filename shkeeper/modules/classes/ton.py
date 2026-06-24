from shkeeper.modules.classes.ethereum import Ethereum


class Ton(Ethereum):
    host_env_prefix = "TON"
    creds_env_prefix = "TON"
    default_host = "ton-shkeeper"
    network_currency = "TON"
    block_interval = 0.4
    sync_lag_multiplier = 900

    def _status_block_timestamp(self, response):
        return int(response["last_block_timestamp"])
