from abc import abstractmethod
from decimal import Decimal
from os import environ
import datetime
import json
from collections import namedtuple

import requests

from shkeeper.modules.classes.crypto import Crypto


class TronToken(Crypto):

    has_autopayout = False
    network_currency = 'TRX'
    account_activation_fee = 1.1  # https://developers.tron.network/docs/account#account-activation

    def gethost(self):
        host = environ.get('TRON_API_SERVER_HOST', 'localhost')
        port = environ.get('TRON_API_SERVER_PORT', '6000')
        return f'{host}:{port}'

    def get_auth_creds(self):
        username = environ.get(f"{self.crypto}_USERNAME", "shkeeper")
        password = environ.get(f"{self.crypto}_PASSWORD", "shkeeper")
        return (username, password)

    def balance(self):
        try:
            response = requests.post(
                f'http://{self.gethost()}/{self.crypto}/balance',
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)
            balance = response['balance']
        except requests.exceptions.RequestException:
            balance = False

        return Decimal(balance)

    def getstatus(self):
        try:
            response = requests.post(
                f'http://{self.gethost()}/{self.crypto}/status',
                auth=self.get_auth_creds(),
            ).json(parse_float=Decimal)

            block_ts =  response['last_block_timestamp']
            now_ts = int(datetime.datetime.now().timestamp())

            delta = abs(now_ts - block_ts)
            block_interval = 3
            if delta < block_interval * 10:
                return "Synced"
            else:
                return "Sync In Progress (%d blocks behind)" % (delta // block_interval)

        except Exception as e:
            return "Offline"

    def mkaddr(self):
        response = requests.post(
                f'http://{self.gethost()}/{self.crypto}/generate-address',
                auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        addr = response['base58check_address']
        return addr

    def getaddrbytx(self, txid):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/transaction/{txid}',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response['address'], Decimal(response['amount']), response['confirmations'], response['category']

    def dump_wallet(self):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/dump',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)

        now = datetime.datetime.now().strftime("%F_%T")
        filename = f"{now}_{self.crypto}_shkeeper_wallet.json"
        content = json.dumps(response['accounts'], indent=4)
        return filename, content

    def create_wallet(self, *args, **kwargs):
        return {'error': None}

    @property
    def fee_deposit_account(self):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/fee-deposit-account',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)

        FeeDepositAccount = namedtuple('FeeDepositAccount', 'addr balance')
        return FeeDepositAccount(response['account'], response['balance'])

    def estimate_tx_fee(self, amount):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/calc-tx-fee/{amount}',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def mkpayout(self, destination, amount, fee):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

    def get_task(self, id):
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/task/{id}',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response