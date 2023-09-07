from abc import abstractmethod
from os import environ
import json
import requests
import datetime
from collections import namedtuple
from decimal import Decimal
from flask import current_app as app
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.ethereum import Ethereum




class Bnb(Ethereum):

    network_currency = 'BNB'

    def gethost(self):
        host = environ.get('BNB_API_SERVER_HOST', 'bnb-shkeeper')
        port = environ.get('BNB_SERVER_PORT', '6000')
        return f'{host}:{port}'


    def get_auth_creds(self):
        username = environ.get(f"BNB_USERNAME", "shkeeper")
        password = environ.get(f"BNB_PASSWORD", "shkeeper")
        return (username, password)


    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False): 
        if self.crypto == self.network_currency and subtract_fee_from_amount:
            fee = Decimal(self.estimate_tx_fee(amount)['fee'])
            if fee >= amount:
                return f"Payout failed: not enought BNB to pay for transaction. Need {fee}, balance {amount}"
            else:
                amount -= fee
        response = requests.post(
            f'http://{self.gethost()}/{self.crypto}/payout/{destination}/{amount}',
            auth=self.get_auth_creds(),
        ).json(parse_float=Decimal)
        return response

