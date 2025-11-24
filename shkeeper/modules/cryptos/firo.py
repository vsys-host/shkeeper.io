from decimal import Decimal
from shkeeper import requests

from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class firo(BitcoinLikeCrypto):
    wallet_created = True

    def __init__(self):
        self.crypto = "FIRO"

    def getname(self):
        return "Firo"

    def gethost(self):
        return "firod:8332"
    
    def balance(self):
        try:
            response = requests.post(
                "http://" + self.gethost(),
                auth=self.get_rpc_credentials(),
                json=self.build_rpc_request("getbalance"),
            ).json(parse_float=Decimal)
            balance = response["result"]
        except requests.exceptions.RequestException:
            balance = False

        return balance
    
    def getaddrbytx(self, txid):
        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("gettransaction", txid),
        ).json(parse_float=Decimal)

        if response["error"]:
            raise Exception(
                f"failed to get details of txid {txid}: {response['error']=}"
            )

        details = []
        regular_transfers = []
        print(response["result"]["details"])
        for transfer in response["result"]["details"]:
            if ("address" in transfer.keys() and # FIRO-SPARK results [{'account': '', 'category': 'receive', 'amo.....
                len(transfer["address"]) < 140): # It is not a firo-spark payout with address
                regular_transfers.append(transfer)
        
        if len(regular_transfers) == 0: 
            raise Exception(
                f"Do not find FIRO transactions in {txid}, skip it "
            )

        for i in regular_transfers:
            details.append(
                [
                    i["address"],
                    i["amount"],
                    response["result"]["confirmations"],
                    i["category"],
                ]
            )
        if details:
            return details
        else:
            raise Exception(
                f"failed to find details in txid {txid}: {response['result']}"
            )
    
