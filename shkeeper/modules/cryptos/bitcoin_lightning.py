from collections import namedtuple
import datetime
from functools import cached_property
from os import environ, path, unlink
import base64, codecs, json, requests
import threading
from time import sleep, time
from decimal import Decimal
from typing import List, Literal, Tuple

from flask import current_app as app

from shkeeper.events import shkeeper_initialized
from shkeeper.models import BitcoinLightningInvoice as BLI, Setting
from shkeeper.modules.classes.crypto import Crypto
from shkeeper import db
from shkeeper.utils import format_decimal, remove_exponent
from shkeeper.wallet_encryption import wallet_encryption


class BitcoinLightning(Crypto):
    _display_name = "BTC Lightning"

    def __init__(self) -> None:
        self.crypto = "BTC-LIGHTNING"

        self.RTL_WEB_URL = environ.get("RTL_WEB_URL", "http://127.0.0.1:3000")

        # Handle LNBITS_URL with proper validation and normalization
        lnbits_url = environ.get("LNBITS_URL")
        if lnbits_url:
            # Strip trailing slashes
            lnbits_url = lnbits_url.rstrip("/")
            # Add https:// prefix if no scheme is present
            if not lnbits_url.startswith(("http://", "https://")):
                lnbits_url = f"https://{lnbits_url}"
            self.LNBITS_URL = lnbits_url
        else:
            raise ValueError("LNBITS_URL is not set")

        self.LNBITS_ADMIN_PASSWORD = environ.get("LNBITS_ADMIN_PASSWORD")
        self.LNBITS_SHARED_DIR = environ.get("LNBITS_SHARED_DIR", "/lnbits_shared")

        self.LND_SHARED_DIR = environ.get("LND_SHARED_DIR", "/lightning_shared")
        self.LND_REST_URL = environ.get("LND_REST_URL", "https://lnd:8080")
        self.LND_NETWORK = environ.get(
            "LND_NETWORK",
            "mainnet",  # regtest, testnet, mainnet
        )
        self.LIGHTNING_INVOICE_TTL = int(
            environ.get("LIGHTNING_INVOICE_TTL", 60 * 60 * 24 * 7)
        )
        self.LIGHTNING_INVOICE_REFRESH_PERIOD = int(
            environ.get("LIGHTNING_INVOICE_REFRESH_PERIOD", 3)
        )
        self.LIGHTNING_INVOICE_ERROR_WAIT_PERIOD = int(
            environ.get("LIGHTNING_INVOICE_ERROR_WAIT_PERIOD", 60)
        )
        self.LIGHTNING_SEND_TO_SHKEEPER_PERIOD = int(
            environ.get("LIGHTNING_SEND_TO_SHKEEPER_PERIOD", 1)
        )

        self.LIGHTNING_REQUESTS_TIMEOUT = int(
            environ.get("LIGHTNING_REQUESTS_TIMEOUT", 60)
        )

        self.LIGHTNING_WALLET_UNLOCK_PERIOD = int(
            environ.get("LIGHTNING_WALLET_UNLOCK_PERIOD", 5)
        )

        self.LIGHTNING_WALLET_SEED_SAVER_PERIOD = int(
            environ.get("LIGHTNING_WALLET_SEED_SAVER_PERIOD", 5)
        )

        self.LIGHTNING_GENERATE_ONCHAIN_ADDRESS = bool(
            environ.get("LIGHTNING_GENERATE_ONCHAIN_ADDRESS", False)
        )

        self._lnurl = None

        self.start_threads()

    def start_threads(self):
        threading.Thread(
            target=self.invoice_listener,
            name="invoice listener",
            daemon=True,
            args=(app._get_current_object(),),
        ).start()

        threading.Thread(
            target=self.invoice_refresher,
            name="invoice refresher",
            daemon=True,
            args=(app._get_current_object(),),
        ).start()

        threading.Thread(
            target=self.invoice_notificator,
            name="invoice notificator",
            daemon=True,
            args=(app._get_current_object(),),
        ).start()

        # threading.Thread(
        #     target=self.wallet_unlocker,
        #     name="wallet_unlocker",
        #     daemon=True,
        #     args=(app._get_current_object(),),
        # ).start()

        threading.Thread(
            target=self.seed_saver,
            name="seed saver",
            daemon=True,
            args=(app._get_current_object(),),
        ).start()

        threading.Thread(
            target=self.lnurl_setup,
            name="lnurl setup",
            daemon=True,
            args=(app._get_current_object(),),
        ).start()

    def getname(self):
        return self.crypto

    def gethost(self):
        return self.LND_REST_URL

    @cached_property
    def session(self):
        s = requests.Session()
        s.verify = self.tls_cert
        s.headers = {"Grpc-Metadata-macaroon": self.macaroon}
        return s

    @cached_property
    def macaroon(self):
        macaroon_path = path.join(
            self.LND_SHARED_DIR,
            "data/chain/bitcoin",
            self.LND_NETWORK,
            "admin.macaroon",
        )
        return codecs.encode(open(macaroon_path, "rb").read(), "hex")

    @property
    def rtl_cookie(self):
        return open(
            path.join(
                self.LND_SHARED_DIR,
                "rtl-cookie",
            ),
        ).read()

    @cached_property
    def tls_cert(self):
        return path.join(
            self.LND_SHARED_DIR,
            "tls.cert",
        )

    def getstatus(self) -> str:
        try:
            info = self.session.get(
                f"{self.LND_REST_URL}/v1/getinfo",
                timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
            ).json()
            if "message" in info:
                return info["message"]
            if info["synced_to_chain"]:
                status = "Synced"
            else:
                block_ts = int(info["best_header_timestamp"])
                now_ts = int(datetime.datetime.now().timestamp())
                delta = abs(now_ts - block_ts)
                status = f"{delta} seconds lag"
            return status
        except Exception as e:
            app.logger.exception(f"Can't get status: {e}")
            return "Offline"

    @staticmethod
    def sat_to_btc(sat: Decimal):
        return sat / 100_000_000

    @staticmethod
    def msat_to_btc(msat: Decimal):
        return msat / 100_000_000_000

    @staticmethod
    def btc_to_sat(btc: Decimal):
        return btc * 100_000_000

    @staticmethod
    def btc_to_msat(btc: Decimal):
        return btc * 100_000_000_000

    def balance(self) -> Decimal:
        try:
            balance_response = self.session.get(
                f"{self.LND_REST_URL}/v1/balance/channels",
                timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
            )
            r = balance_response.json()
            if balance_response.status_code > 200:
                app.logger.warning(f"Can't get balance: {r['message']}")
                return Decimal(0)
            else:
                return self.sat_to_btc(Decimal(r["balance"]))
        except Exception as e:
            app.logger.exception(f"Can't get balance: {e}")
            return Decimal(0)

    @staticmethod
    def to_hex_string(b64_string):
        return codecs.encode(base64.b64decode(b64_string), "hex").decode()

    @staticmethod
    def to_base64_string(hex_string):
        return base64.b64encode(codecs.decode(hex_string, "hex")).decode()

    def mkaddr(self, **kwargs) -> str:
        data = {
            "value": 0,
            "expiry": self.LIGHTNING_INVOICE_TTL,
        }
        data.update(kwargs.get("details", {}))
        data.update({"value": int(self.btc_to_sat(data["value"]))})

        invoices_response = self.session.post(
            f"{self.LND_REST_URL}/v1/invoices",
            data=json.dumps(data),
            timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
        )
        r = invoices_response.json()
        r["r_hash"] = self.to_hex_string(r["r_hash"])
        bli = BLI()
        bli.update(**r)
        return r["payment_request"]

    def invoice_listener(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        while True:
            with app.app_context():
                try:
                    r = self.session.get(
                        f"{self.LND_REST_URL}/v1/invoices/subscribe",
                        stream=True,
                        timeout=None,
                    )
                    if r.status_code > 200:
                        raise Exception(f"Invoice listener subscribing error: {r.text}")
                    for raw_response in r.iter_lines():
                        json_response = json.loads(raw_response)
                        app.logger.debug(f"invoice update: {json_response}")
                        r = json_response["result"]
                        r["r_hash"] = self.to_hex_string(r["r_hash"])
                        if inv := BLI.query.filter(BLI.r_hash == r["r_hash"]).first():
                            inv.update(**r)
                        else:
                            app.logger.debug(
                                f"invoice not (yet) found in db. Update body: {json_response}"
                            )
                except Exception as e:
                    app.logger.exception(f"error: {e}")
                    sleep(self.LIGHTNING_INVOICE_ERROR_WAIT_PERIOD)

    def invoice_refresher(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        inactive_statuses = ("SETTLED", "CANCELED")
        while True:
            sleep(self.LIGHTNING_INVOICE_REFRESH_PERIOD)
            with app.app_context():
                try:
                    unpaid_invoices = BLI.query.filter(
                        (BLI.state.not_in(inactive_statuses)) | BLI.state.is_(None)
                    ).all()
                    if len(unpaid_invoices):
                        app.logger.debug(
                            f"db has {len(unpaid_invoices)} unpaid invoces"
                        )
                    for inv in unpaid_invoices:
                        r = self.session.get(
                            f"{self.LND_REST_URL}/v1/invoice/{inv.r_hash}",
                            timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
                        ).json()
                        r["r_hash"] = self.to_hex_string(r["r_hash"])
                        inv.update(**r)
                except Exception as e:
                    app.logger.exception(f"error: {e}")

    def invoice_notificator(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        s = requests.Session()
        s.headers = {
            "X-Shkeeper-Backend-Key": environ.get(
                "SHKEEPER_BTC_BACKEND_KEY", "shkeeper"
            )
        }
        while True:
            sleep(self.LIGHTNING_SEND_TO_SHKEEPER_PERIOD)
            with app.app_context():
                try:
                    paid_invoices = BLI.query.filter(
                        (BLI.state == "SETTLED") & (BLI.sent_to_shkeeper == False)
                    ).all()
                    if len(paid_invoices):
                        app.logger.debug(f"{len(paid_invoices)} notifications pending")
                    for inv in paid_invoices:
                        app.logger.debug(f"sending notification for {inv.r_hash}")
                        r = s.post(
                            f"http://localhost:5000/api/v1/walletnotify/{self.crypto}/{inv.r_hash}",
                            timeout=300,
                        )
                        app.logger.debug(f"{inv.r_hash} response: {r.text}")
                        r = r.json()
                        if "success" == r["status"]:
                            inv.update(sent_to_shkeeper=True)

                except Exception as e:
                    app.logger.exception(f"error: {e}")

    def wallet_unlocker(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        while True:
            with app.app_context():
                try:
                    key = wallet_encryption.wait_for_key()
                    wallet_password = base64.b64encode(key.zfill(8).encode()).decode()

                    unlockwallet_response = self.session.post(
                        f"{self.LND_REST_URL}/v1/unlockwallet",
                        data=json.dumps(
                            {
                                "wallet_password": wallet_password,
                            }
                        ),
                        timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
                    )
                    r = unlockwallet_response.json()

                    if unlockwallet_response.status_code > 200:
                        if "wallet already unlocked" not in r["message"]:
                            app.logger.debug(f"unlockwallet api error: {r['message']}")
                    else:
                        app.logger.info("wallet has been unlocked!")

                except Exception as e:
                    app.logger.exception(f"error: {e}")

            sleep(self.LIGHTNING_WALLET_UNLOCK_PERIOD)

    def seed_saver(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        while True:
            sleep(self.LIGHTNING_WALLET_SEED_SAVER_PERIOD)
            with app.app_context():
                try:
                    setting_name = "btc_lightning_wallet_seed"
                    setting = Setting.query.get(setting_name)
                    if setting:
                        app.logger.debug("seed is already saved to db")
                        break

                    seed_path = path.join(
                        self.LND_SHARED_DIR,
                        "wallet-seed",
                    )
                    app.logger.debug(f"Reading seed from {seed_path}...")
                    cipher_seed_mnemonic = open(seed_path, "rb").read().decode()

                    app.logger.debug(f"Encrypting seed...")
                    encrypted_seed = wallet_encryption.encrypt_text(
                        cipher_seed_mnemonic
                    )

                    app.logger.debug(f"Saving enctypted seed to db...")
                    db.session.add(Setting(name=setting_name, value=encrypted_seed))
                    db.session.commit()
                    app.logger.debug(f"seed saved.")

                    app.logger.debug(f"removing seed file {seed_path}...")
                    unlink(seed_path)
                    break

                except Exception as e:
                    app.logger.exception(f"error: {e}")

        app.logger.debug(f"thread exiting.")

    def lnurl_setup(self, app):
        app.logger.debug(f"waiting for shkeeper initialization...")
        shkeeper_initialized.wait()
        app.logger.debug(f"received shkeeper initialization signal!")

        sleep(5)  # Wait for LNbits to be ready

        with app.app_context():
            while True:
                try:
                    app.logger.debug("Fetching existing LNURL-pay links from LNbits...")

                    # Fetch existing LNURL-pay links
                    response = self.lnbits_session.get(
                        f"{self.LNBITS_URL}/lnurlp/api/v1/links",
                    )

                    if response.status_code == 200:
                        links = response.json()
                        app.logger.debug(f"Found {len(links)} existing LNURL links")

                        # Look for ShKeeper wallet LNURL
                        for link in links:
                            app.logger.debug(f"Examining LNURL: {link}")
                            if (
                                link.get("description")
                                == "ShKeeper BTC Lightning Wallet"
                            ):
                                self._lnurl = link["lnurl"]
                                app.logger.debug(f"Using existing LNURL: {self._lnurl}")
                                break

                    # Create new LNURL if not found
                    if not self._lnurl:
                        app.logger.debug("Creating new LNURL-pay link via LNbits...")

                        lnurl_data = {
                            "description": "ShKeeper BTC Lightning Wallet",
                            "min": 1,  # 1 satoshi
                            "max": 100_000_000,  # 1 BTC in satoshis
                            "comment_chars": 255,
                        }

                        response = self.lnbits_session.post(
                            f"{self.LNBITS_URL}/lnurlp/api/v1/links",
                            json=lnurl_data,
                        )

                        if response.status_code != 201:
                            app.logger.error(f"Failed to create LNURL: {response.text}")
                            sleep(30)
                            continue

                        result = response.json()
                        self._lnurl = result["lnurl"]
                        app.logger.debug(f"LNURL created: {self._lnurl}")

                    break

                except Exception as e:
                    app.logger.exception(f"error: {e}")
                    sleep(30)

        app.logger.debug(f"thread exiting.")

    def getaddrbytx(
        self, txid
    ) -> List[Tuple[str, Decimal, int, Literal["send", "receive"]]]:
        inv: BLI = BLI.query.filter(BLI.r_hash == txid).first()
        confirmations = 999
        address = inv.payment_request
        amount = self.sat_to_btc(inv.value)
        operation = "receive"
        info = (address, amount, confirmations, operation)
        return [info]

    def get_confirmations_by_txid(self, txid) -> int:
        return 999

    def estimate_tx_fee(self, amount, **kwargs):
        pay_req, lnurl_info = self.lnurl_to_pr(kwargs["address"])
        app.logger.debug(f"Estimated TX fee for {pay_req}:")
        decoded_pay_req = self.session.get(
            f"{self.LND_REST_URL}/v1/payreq/{pay_req}",
            timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
        ).json()
        app.logger.debug(f"{decoded_pay_req!r}")
        if "destination" not in decoded_pay_req:
            return {
                "status": "error",
                "error": (
                    decoded_pay_req["message"]
                    if "message" in decoded_pay_req
                    else f"{decoded_pay_req!r}"
                ),
            }

        expiration_ts = int(decoded_pay_req["timestamp"]) + int(
            decoded_pay_req["expiry"]
        )
        exp_date = datetime.datetime.fromtimestamp(expiration_ts).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if expiration_ts <= time():
            return {
                "status": "error",
                "error": f"The invoice has been expired. Expiration date: {exp_date}",
            }

        return {
            "status": "success",
            "fee": 0,
            # "fee_estimate_details": fee_estimate,
            "payment_request_details": decoded_pay_req,
            "lnurl_info": lnurl_info,
        }

    def mkpayout(
        self,
        destination: str,
        amount: Decimal,
        fee: int,
        subtract_fee_from_amount: bool = False,
    ):
        destination, lnurl_info = self.lnurl_to_pr(
            destination, remove_exponent(self.btc_to_msat(amount))
        )

        try:
            result = self.session.post(
                f"{self.LND_REST_URL}/v1/channels/transactions",
                data=json.dumps(
                    {
                        "payment_request": destination,
                    }
                ),
                timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
            ).json()

            app.logger.debug(f"Payout result: {result!r}")

            if result["payment_error"]:
                return {"result": None, "error": {"message": result["payment_error"]}}
            else:
                return {
                    "result": self.to_hex_string(result["payment_hash"]),
                    "error": None,
                }

        except Exception as e:
            app.logger.exception("")
            return {"result": None, "error": {"message": str(e)}}

    def create_wallet(self):
        # moved to lndinit
        return {"error": None}

        try:
            app.logger.debug(f"waiting for shkeeper encryption key...")

            key = wallet_encryption.wait_for_key()
            wallet_password = base64.b64encode(key.zfill(8).encode()).decode()

            app.logger.debug(f"unlocking wallet with key...")

            # 1. Try unlock existing wallet

            unlockwallet_response = self.session.post(
                f"{self.LND_REST_URL}/v1/unlockwallet",
                data=json.dumps(
                    {
                        "wallet_password": wallet_password,
                    }
                ),
                timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
            )
            r = unlockwallet_response.json()
            if (
                unlockwallet_response.status_code == 200
                or "wallet already unlocked" in r["message"]
            ):
                app.logger.debug(f"Wallet unlocked!")
                return {"error": None}

            else:
                app.logger.debug(f"unlockwallet api error: {r['message']!r}")

                # 2. Create wallet if does not exist

                app.logger.debug(f"Preparing to create a new wallet...")

                # 2.1 generate seed
                app.logger.debug(f"Generating seed...")

                genseed_response = self.session.get(
                    f"{self.LND_REST_URL}/v1/genseed",
                    timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
                )
                r = genseed_response.json()
                if genseed_response.status_code > 200:
                    return {"error": r}

                cipher_seed_mnemonic = r["cipher_seed_mnemonic"]

                # 2.2 save encrypted seed
                app.logger.debug(f"Saving seed...")

                encrypted_seed = wallet_encryption.encrypt_text(
                    " ".join(cipher_seed_mnemonic)
                )

                setting_name = "btc_lightning_wallet_seed"
                setting = Setting.query.get(setting_name)
                if setting:
                    return {
                        "error": "Seed already exists in db. Refusing to create a new wallet."
                    }
                else:
                    db.session.add(Setting(name=setting_name, value=encrypted_seed))
                    db.session.commit()
                    app.logger.debug(f"Encrypted seed saved to db.")

                # 2.3 creare new wallet using seed

                app.logger.debug(f"Initializing a new wallet using generated seed...")
                initwallet_response = self.session.post(
                    f"{self.LND_REST_URL}/v1/initwallet",
                    data=json.dumps(
                        {
                            "wallet_password": wallet_password,
                            "cipher_seed_mnemonic": cipher_seed_mnemonic,
                        }
                    ),
                    timeout=self.LIGHTNING_REQUESTS_TIMEOUT,
                )
                r = initwallet_response.json()
                if initwallet_response.status_code == 200:
                    app.logger.debug(f"Wallet has been created.")
                    return {"error": None}
                else:
                    return {"error": r}

        except Exception as e:
            app.logger.exception(e)
            return {"error": str(e)}

    def dump_wallet(self) -> Tuple[str, str]:
        setting_name = "btc_lightning_wallet_seed"
        setting = Setting.query.get(setting_name)
        content = wallet_encryption.decrypt_text(setting.value)
        filename = "shkeeper-btc-lightning-mnemonic-key.txt"
        return filename, content

    @property
    def wallet(self):
        return self._wallet.query.filter_by(crypto=self.crypto).first()

    def get_all_addresses(self) -> List[str]:
        return [invoice.payment_request for invoice in BLI.query.all()]

    #
    # LNURL
    #

    @property
    def lnbits_admin_apikey(self):
        return open(
            path.join(
                self.LNBITS_SHARED_DIR,
                "data/.lnbits_admin_key",
            ),
        ).read()

    @cached_property
    def lnbits_session(self):
        s = requests.Session()
        s.verify = False
        s.headers = {"X-API-KEY": self.lnbits_admin_apikey}
        return s

    def lnbits_decode_lnurl(self, lnurl):
        app.logger.debug(f"lnbits_decode_lnurl called with lnurl={lnurl}")
        app.logger.debug(f"Posting to {self.LNBITS_URL}/api/v1/lnurlscan")
        result = self.lnbits_session.post(
            f"{self.LNBITS_URL}/api/v1/lnurlscan", json={"lnurl": lnurl}
        ).json()
        app.logger.debug(f"lnbits_decode_lnurl result: {result}")
        return result

    def lnurl_to_pr(self, destination, amount=None):
        app.logger.debug(
            f"lnurl_to_pr called with destination={destination}, amount={amount}"
        )
        try:
            app.logger.debug(f"Decoding LNURL: {destination}")
            lnurl_info = self.lnbits_decode_lnurl(destination)
            app.logger.debug(f"LNURL decoded: {lnurl_info}")

            if amount is None:
                amount = lnurl_info["minSendable"]

            callback_url = f"{lnurl_info['callback']}?amount={amount}"
            app.logger.debug(f"Requesting payment request from: {callback_url}")
            lnurl_pr_info = requests.get(callback_url).json()
            app.logger.debug(f"Payment request response: {lnurl_pr_info}")

            new_destination = lnurl_pr_info["pr"]
            app.logger.debug(
                f"Successfully converted LNURL to payment request: {new_destination}"
            )
            return new_destination, lnurl_info
        except Exception as e:
            app.logger.debug(
                f"Failed to convert LNURL, using original destination. Error: {e}"
            )
            return destination, None

    def get_lnurl(self):
        return self._lnurl

    @property
    def fee_deposit_account(self):
        FeeDepositAccount = namedtuple("FeeDepositAccount", "addr balance")
        return FeeDepositAccount(self.get_lnurl(), self.balance())
