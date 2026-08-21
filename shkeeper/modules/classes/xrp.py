from shkeeper.modules.classes.ethereum import Ethereum


class Xrp(Ethereum):
    host_env_prefix = "XRP"
    creds_env_prefix = "XRP"
    default_host = "xrp-shkeeper"
    network_currency = "XRP"
    block_interval = 4

    def _status_block_timestamp(self, response):
        return int(response["last_block_timestamp"]) + 946684800

    def _subtract_payout_fee(self, amount, fee):
        # 10 XRP need to keep the fee-deposit account active
        return amount - fee - 10
