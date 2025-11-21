from decimal import Decimal
from os import environ
from shkeeper import requests

from shkeeper.modules.classes.bitcoin_like_crypto import BitcoinLikeCrypto


class firo_spark(BitcoinLikeCrypto):
    wallet_created = True

    def __init__(self):
        self.crypto = "FIRO-SPARK"

    def getname(self):
        return "Firo-Spark"

    def gethost(self):
        return "firod:8332"
    
    def tofiro(self, ufiro_amount):
        return Decimal(ufiro_amount / 100_000_000)
    
    def tosat(self, firo_amount):
        return int(Decimal(firo_amount) * 100_000_000)

    def get_rpc_credentials(self):
        username = environ.get("FIRO_USERNAME", "shkeeper")
        password = environ.get("FIRO_PASSWORD", "shkeeper")
        return (username, password)    
     
    def build_spendspark_request(self, method, params_list):
        rrr = {"jsonrpc": "1.0", 
                "id": "shkeeper", 
                "method": method, 
                "params": [{params_list[0]:{
                           "amount":float(self.tofiro(params_list[1])),
                           "memo":"",
                           "subtractFee": params_list[2]}}]}
        return rrr
    

    
    def balance(self):
        try:
            response = requests.post(
                "http://" + self.gethost(),
                auth=self.get_rpc_credentials(),
                json=self.build_rpc_request("getsparkbalance", ),
            ).json(parse_float=Decimal)
            balance = self.tofiro(response["result"]["availableBalance"])
        except requests.exceptions.RequestException:
            balance = False

        return balance

    def mkpayout(self, destination, amount, fee, subtract_fee_from_amount=False):
        btc_per_kb = "%.8f" % (float(fee) / 100000)

        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("settxfee", btc_per_kb),
        ).json(parse_float=Decimal)
        if response["error"]:
            return response

        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_spendspark_request(
                "spendspark",
                [
                destination,
                self.tosat(amount.normalize()),
                subtract_fee_from_amount,
                ]
            ),
        ).json(parse_float=Decimal)

        return response

    def mkaddr(self, **kwargs):
        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("getnewsparkaddress"),
        ).json(parse_float=Decimal)
        addr = response["result"][0]
        return addr

    def getaddrbytx(self, txid):
        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("getsparkcoinaddr", txid),
        ).json(parse_float=Decimal)

        firo_response = requests.post( # only to get confirmations
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("gettransaction", txid),
        ).json(parse_float=Decimal)


        if response["error"]:
            raise Exception(
                f"Failed to get details of txid {txid}: {response['error']=}"
            )
        
        if len(response["result"]) == 0:
            raise Exception(
                f"Transaction {txid}: is a FIRO transaction, skip it "
            )
        
        if firo_response["error"]:
            raise Exception(
                f"Failed to get details of txid {txid}: {firo_response['error']=}"
            )

        details = []
        for i, transfer in enumerate(response["result"]):
            if firo_response["result"]["details"][i]["category"] == 'receive':
                details.append(
                    [
                        transfer["address"],
                        transfer["amount"],
                        firo_response["result"]["confirmations"],
                        firo_response["result"]["details"][i]["category"],
                    ]
                )
            elif firo_response["result"]["details"][i]["category"] == 'spend': # replace firo-spark category "spend" to "send"
                details.append(
                    [
                        transfer["address"],
                        firo_response["result"]["details"][i]["amount"],
                        firo_response["result"]["confirmations"],
                        "send",
                    ]
                )
        if details:
            return details
        else:
            raise Exception(
                f"failed to find details in txid {txid}: {response['result']}"
            )

    def get_confirmations_by_txid(self, txid):
        _, _, confirmations, _ = self.getaddrbytx(txid)[0]
        return confirmations

    def get_all_addresses(self):
        response = requests.post(
            "http://" + self.gethost(),
            auth=self.get_rpc_credentials(),
            json=self.build_rpc_request("getallsparkaddresses"),
        ).json(parse_float=Decimal)
        return (
            [response["result"][addr_key] for addr_key in response["result"].keys()]
            if response["result"]
            else []
        )
    
    
