import traceback
from os import environ
from concurrent.futures import ThreadPoolExecutor
from operator import  itemgetter


from werkzeug.datastructures import Headers
from flask import jsonify
from flask import request
from flask import Response
from flask import stream_with_context
from flask_smorest import Blueprint as SmorestBlueprint
from marshmallow import Schema, fields

from shkeeper import requests
from shkeeper.auth import basic_auth_optional, login_required, api_key_required
from shkeeper.modules.classes.tron_token import TronToken
from shkeeper.modules.classes.ethereum import Ethereum
from shkeeper.modules.cryptos.bitcoin_lightning import BitcoinLightning
from shkeeper.modules.cryptos.monero import Monero
from shkeeper.models import *
from shkeeper.callback import send_notification, send_unconfirmed_notification
from shkeeper.utils import format_decimal
from shkeeper.wallet_encryption import (
    wallet_encryption,
    WalletEncryptionPersistentStatus,
    WalletEncryptionRuntimeStatus,
)
from shkeeper.exceptions import NotRelatedToAnyInvoice


# =========================
# Marshmallow Schemas
# =========================
# TODO: schemas into separate file
class ErrorSchema(Schema):
    status = fields.String(required=True, example="error")
    message = fields.String(required=True)
    traceback = fields.String(load_default=None)

class SuccessSchema(Schema):
    status = fields.String(required=True, example="success")

class CryptoSchema(Schema):
    name = fields.String(required=True, description="Crypto currency name")
    display_name = fields.String(required=True)

class GetCryptoResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    crypto = fields.List(fields.String(), required=True)
    crypto_list = fields.List(fields.Nested(CryptoSchema), required=True)

class GenerateAddressResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    addr = fields.String(required=True)

class PaymentRequestSchema(Schema):
    # Keep liberal request schema because Invoice.add(...) accepts dynamic fields
    fiat = fields.String(load_default=None)
    amount = fields.String(load_default=None)
    # Unknown keys will pass through because we use as_kwargs=False and forward dict as-is

class PaymentResponseSchema(Schema):
    # We keep a generic schema because invoice.for_response() returns a flat dict
    status = fields.String(required=True, example="success")

class QuoteRequestSchema(Schema):
    fiat = fields.String(required=True, example="USD")
    amount = fields.String(required=True, example="10.00")

class QuoteResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    fiat = fields.String(required=True)
    amount_fiat = fields.String(required=True)
    crypto = fields.String(required=True)
    amount_crypto = fields.String(required=True)
    exchange_rate = fields.String(required=True)

class GatewayStatusResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    enabled = fields.Boolean(required=True)
    token = fields.String(required=True)

class GatewaySetRequestSchema(Schema):
    enabled = fields.Boolean(required=True)

class GatewayTokenRequestSchema(Schema):
    token = fields.String(required=True)

class TransactionRequestSchema(Schema):
    # Keep flexible; Transaction.add(...) accepts dict with various keys
    txid = fields.String(load_default=None)
    amount = fields.String(load_default=None)

class TransactionResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    id = fields.Integer(required=True)

class PayoutDestinationRequestSchema(Schema):
    action = fields.String(required=True, example="add")  # add | delete | list
    daddress = fields.String(load_default=None)
    comment = fields.String(load_default=None)

class PayoutDestinationListItemSchema(Schema):
    addr = fields.String(required=True)
    comment = fields.String(allow_none=True)

class PayoutDestinationListResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    payout_destinations = fields.List(fields.Nested(PayoutDestinationListItemSchema))

class AutoPayoutRequestSchema(Schema):
    policy = fields.String(required=True)
    policyValue = fields.String(required=True)
    policyStatus = fields.Boolean(load_default=True)
    add = fields.String(load_default=None)   # autopayout destination
    fee = fields.String(load_default=None)
    partiallPaid = fields.Boolean(required=True)
    addedFee = fields.Boolean(required=True)
    confirationNum = fields.Integer(required=True)
    recalc = fields.Boolean(required=True)

class StatusResponseSchema(Schema):
    name = fields.String(required=True)
    amount = fields.String(required=True)
    server = fields.String(required=True)

class PayoutRequestSchema(Schema):
    destination = fields.String(required=True)
    amount = fields.String(required=True)
    fee = fields.String(required=True)

class BackendKeyErrorSchema(Schema):
    status = fields.String(example="error")
    message = fields.String(example="No backend key provided")

class DecryptResponseSchema(Schema):
    persistent_status = fields.String(required=True)
    runtime_status = fields.String(required=True)
    key = fields.String(allow_none=True)

class ServerDetailsResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    key = fields.String(required=True, description="user:password")
    host = fields.String(required=True)

class ExchangeRateSetRequestSchema(Schema):
    fiat = fields.String(required=True)
    source = fields.String(required=True, example="manual")
    rate = fields.String(load_default=None)
    fee = fields.String(required=True)

class ListAddressesResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    addresses = fields.List(fields.String(), required=True)

class TransactionsListResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    transactions = fields.List(fields.Raw(), required=True)

class InvoicesListResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    invoices = fields.List(fields.Raw(), required=True)

class PayoutsCheckResponseSchema(Schema):
    status = fields.String(required=True, example="success")

class TxInfoResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    info = fields.Dict(keys=fields.String(), values=fields.Raw())

class DecryptionKeyFormSchema(Schema):
    key = fields.String(required=True)

class TestCallbackSchema(Schema):
    _ = fields.Raw(load_default=None)  # arbitrary payload

# =========================
# smorest Blueprint
# =========================

# NOTE: This replaces the old Flask Blueprint. Name and URLs remain the same.
blp_v1 = SmorestBlueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="SHKeeper v1 endpoints"
)

# tiny helper to avoid repeating tags/security on every route
def with_tags(*names):
    def _wrap(fn):
        return blp_v1.doc(tags=list(names))(fn)
    return _wrap

def with_security(*reqs):
    """Usage: @with_security({"API_Key": []}) or @with_security({"Basic": []})"""
    def _wrap(fn):
        return blp_v1.doc(security=list(reqs))(fn)
    return _wrap

@blp_v1.route("/crypto")
@with_tags("Cryptos")
@blp_v1.route("/crypto")
@blp_v1.doc(
    **{
        "x-codeSamples": [
            {"lang": "cURL", "label": "CLI",
             "source": "curl --location --request GET 'https://demo.shkeeper.io/api/v1/crypto'\n"}
        ]
    }
)
@blp_v1.response(200, GetCryptoResponseSchema, example={
    "summary": "Get Available Crypto Currencies",
    "status": "success",
    "crypto": ["BNB", "BTC", "ETH", "LTC", "XRP"],
    "crypto_list": [
        {"name":"BNB","display_name":"BNB"},
        {"name":"BTC","display_name":"Bitcoin"},
        {"name":"ETH","display_name":"Ethereum"},
        {"name":"LTC","display_name":"Litecoin"},
        {"name":"XRP","display_name":"XRP"}],
})
def list_crypto():
    """Get cryptocurrencies.

    Get a list of cryptocurrencies available for operation from SHKeeper (these are the ones that are online and not disabled in the admin panel).
    """
    filtered_list = []
    crypto_list = []
    disable_on_lags = app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
    cryptos =  Crypto.instances.values()
    filtered_cryptos = []

    for crypto in cryptos:
        if crypto.wallet.enabled:
            filtered_cryptos.append(crypto)

    def get_crypto_status(crypto):
        return crypto, crypto.getstatus()

    with ThreadPoolExecutor() as executor:
        results = list(executor.map(get_crypto_status, filtered_cryptos))

    for crypto, status in results:
        if status == "Offline":
            continue
        if disable_on_lags and status != "Synced":
            continue
        filtered_list.append(crypto.crypto)
        crypto_list.append({
            "name": crypto.crypto,
            "display_name": crypto.display_name
        })

    return {
        "status": "success",
        "crypto": sorted(filtered_list),
        "crypto_list": sorted(crypto_list, key=itemgetter("name")),
    }


@blp_v1.get("/<string:crypto_name>/generate-address")
@blp_v1.response(200, GenerateAddressResponseSchema)
@with_security({"basic": []})
@login_required
def generate_address(crypto_name):
    crypto = Crypto.instances[crypto_name]
    addr = crypto.mkaddr()
    return {"status": "success", "addr": addr}


@blp_v1.post("/<string:crypto_name>/payment_request")
@blp_v1.arguments(PaymentRequestSchema, as_kwargs=False)
@blp_v1.response(200, PaymentResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def payment_request(crypto_name):
    try:
        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if not crypto.wallet.enabled:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() != "Synced":
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable because of lagging",
            }

        req = request.get_json(force=True)
        invoice = Invoice.add(crypto=crypto, request=req)
        response = {
            "status": "success",
            **invoice.for_response(),
        }
        app.logger.info({"request": req, "response": response})

    except Exception as e:
        app.logger.exception(f"Failed to create invoice for {req}")
        response = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    return response

@blp_v1.post("/<string:crypto_name>/quote")
@blp_v1.arguments(QuoteRequestSchema, as_kwargs=False)
@blp_v1.response(200, QuoteResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def get_crypto_quote(crypto_name):
    """Return a fiat->crypto quote for the given crypto."""
    try:
        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if not crypto.wallet.enabled:
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable",
            }
        if app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() != "Synced":
            return {
                "status": "error",
                "message": f"{crypto_name} payment gateway is unavailable because of lagging",
            }

        req = request.get_json(force=True)
        fiat = req.get("fiat")
        amount_str = req.get("amount")

        if not fiat or not amount_str:
            return {
                "status": "error",
                "message": "'fiat' and 'amount' are required fields.",
            }

        amount_fiat = Decimal(amount_str)
        rate = ExchangeRate.get(fiat, crypto.crypto)
        amount_crypto, exchange_rate = rate.convert(amount_fiat)

        return {
            "status": "success",
            "fiat": fiat,
            "amount_fiat": str(amount_fiat),
            "crypto": crypto.crypto,
            "amount_crypto": str(amount_crypto),
            "exchange_rate": str(exchange_rate),
        }

    except Exception as e:
        app.logger.exception("Failed to get crypto quote")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.get("/<string:crypto_name>/payment-gateway")
@blp_v1.response(200, GatewayStatusResponseSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def payment_gateway_get_status(crypto_name):
    """Get current payment gateway status and token."""
    crypto = Crypto.instances[crypto_name]
    return {
        "status": "success",
        "enabled": crypto.wallet.enabled,
        "token": crypto.wallet.apikey,
    }


@blp_v1.post("/<string:crypto_name>/payment-gateway")
@blp_v1.arguments(GatewaySetRequestSchema, as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def payment_gateway_set_status(crypto_name):
    """Enable/disable payment gateway."""
    req = request.get_json(force=True)
    crypto = Crypto.instances[crypto_name]
    crypto.wallet.enabled = req["enabled"]
    db.session.commit()
    return {"status": "success"}


@blp_v1.post("/<string:crypto_name>/payment-gateway/token")
@blp_v1.arguments(GatewayTokenRequestSchema, as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def payment_gateway_set_token(crypto_name):
    """Set shared API token for all cryptos."""
    req = request.get_json(force=True)
    for crypto in Crypto.instances.values():
        crypto.wallet.apikey = req["token"]
    db.session.commit()
    return {"status": "success"}


@blp_v1.post("/<string:crypto_name>/transaction")
@blp_v1.arguments(TransactionRequestSchema, as_kwargs=False)
@blp_v1.response(200, TransactionResponseSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def add_transaction(crypto_name):
    """Add a transaction manually."""
    try:
        tx = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
        t = Transaction.add(crypto, tx)

        response = {
            "status": "success",
            "id": t.id,
        }

    except Exception as e:
        app.logger.exception(f"Failed to add transaction for crypto: {crypto_name}")
        response = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    return response


@blp_v1.post("/<string:crypto_name>/payout_destinations")
@blp_v1.arguments(PayoutDestinationRequestSchema, as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.alt_response(200, schema=PayoutDestinationListResponseSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def payout_destinations(crypto_name):
    """Manage payout destinations (add/delete/list)."""
    req = request.get_json(force=True)

    if req["action"] == "add":
        if not PayoutDestination.query.filter_by(
            crypto=crypto_name, addr=req["daddress"]
        ).all():
            pd = PayoutDestination(crypto=crypto_name, addr=req["daddress"])
            if req.get("comment"):
                pd.comment = req["comment"]
            db.session.add(pd)
            db.session.commit()
        return {"status": "success"}
    elif req["action"] == "delete":
        PayoutDestination.query.filter_by(addr=req["daddress"]).delete()
        db.session.commit()
        return {"status": "success"}
    elif req["action"] == "list":
        pd = PayoutDestination.query.filter_by(crypto=crypto_name).all()
        return {
            "status": "success",
            "payout_destinations": [{"addr": p.addr, "comment": p.comment} for p in pd],
        }
    else:
        return {"status": "error", "message": "Unknown action"}


@blp_v1.post("/<string:crypto_name>/autopayout")
@blp_v1.arguments(AutoPayoutRequestSchema, as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def autopayout(crypto_name):
    """Configure auto payout policy for a crypto wallet."""
    req = request.get_json(force=True)

    if req["policy"] not in [i.value for i in PayoutPolicy]:
        return {"status": "error", "message": f"Unknown payout policy: {req['policy']}"}

    w = Wallet.query.filter_by(crypto=crypto_name).first()
    if autopayout_destination := req.get("add"):
        w.pdest = autopayout_destination
    if autopayout_fee := req.get("fee"):
        w.pfee = autopayout_fee
    w.ppolicy = PayoutPolicy(req["policy"])
    w.pcond = req["policyValue"]
    w.payout = req.get("policyStatus", True)
    w.llimit = req["partiallPaid"]
    w.ulimit = req["addedFee"]
    w.confirmations = req["confirationNum"]
    w.recalc = req["recalc"]

    db.session.commit()
    return {"status": "success"}


@blp_v1.get("/<string:crypto_name>/status")
@blp_v1.response(200, StatusResponseSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def status(crypto_name):
    """Return wallet status and on-chain sync state."""
    crypto = Crypto.instances[crypto_name]
    return {
        "name": crypto.getname(),
        "amount": format_decimal(crypto.balance()) if crypto.balance() else 0,
        "server": crypto.getstatus(),
    }


@blp_v1.get("/<string:crypto_name>/balance")
@api_key_required
def balance(crypto_name):
    if crypto_name not in Crypto.instances.keys():
        return {"status": "error", 
                "message": f"Crypto {crypto_name} is not enabled"}
    crypto = Crypto.instances[crypto_name]
    fiat = "USD"
    rate = ExchangeRate.get(fiat, crypto_name)
    current_rate = rate.get_rate()
    crypto_amount = format_decimal(crypto.balance()) if crypto.balance() else 0

    return {
        "name": crypto.crypto,
        "display_name": crypto.display_name,
        "amount_crypto": crypto_amount,
        "rate": current_rate,
        "fiat": "USD",
        "amount_fiat": format_decimal(Decimal(crypto_amount) * Decimal(current_rate)),
        "server_status": crypto.getstatus(),
    }

@blp_v1.post("/<string:crypto_name>/payout")
@blp_v1.arguments(PayoutRequestSchema, as_kwargs=False)
#@blp_v1.response(200, fields.Raw())  # passthrough response from crypto.mkpayout(...)
@blp_v1.alt_response(400, schema=ErrorSchema)
@blp_v1.doc(security=[{"basic": []}])
@basic_auth_optional
@login_required
def payout(crypto_name):
    """Make a single payout."""
    try:
        req = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
        amount = Decimal(req["amount"])
        res = crypto.mkpayout(
            req["destination"],
            amount,
            req["fee"],
        )
    except Exception as e:
        app.logger.exception("Payout error")
        return {"status": "error", "message": f"Error: {e}", "traceback": traceback.format_exc()}

    if "result" in res and res["result"]:
        idtxs = res["result"] if isinstance(res["result"], list) else [res["result"]]
        Payout.add(
            {"dest": req["destination"], "amount": amount, "txids": idtxs}, crypto_name
        )

    return res


@blp_v1.post("/payoutnotify/<string:crypto_name>")
@blp_v1.response(200, SuccessSchema)
@blp_v1.alt_response(403, schema=BackendKeyErrorSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@blp_v1.doc(security=[{"BackendKey": []}])
def payoutnotify(crypto_name):
    """Receive payout completion notifications from backend wallet services."""
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        crypto = Crypto.instances[crypto_name]
        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403

        data = request.get_json(force=True)
        app.logger.info(f"Payout notification: {data}")

        for p in data:
            Payout.add(p, crypto_name)

        return {"status": "success"}
    except Exception as e:
        app.logger.exception("Payout notify error")
        return {"status": "error", "message": f"Error: {e}", "traceback": traceback.format_exc()}


@blp_v1.route("/walletnotify/<string:crypto_name>/<string:txid>")
@blp_v1.response(200, SuccessSchema)
@blp_v1.alt_response(403, schema=BackendKeyErrorSchema)
@blp_v1.alt_response(409, schema=ErrorSchema)
@blp_v1.doc(security=[{"BackendKey": []}])
def walletnotify(crypto_name, txid):
    """Receive on-chain tx notifications from backend wallet services."""
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "success",
                "message": f"Ignoring notification for {crypto_name}: crypto is not available for processing",
            }

        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403

        for addr, amount, confirmations, category in crypto.getaddrbytx(txid):
            try:
                if category not in ("send", "receive"):
                    app.logger.warning(
                        f"[{crypto.getname()}/{txid}] ignoring unknown category: {category}"
                    )
                    continue

                if category == "send":
                    Transaction.add_outgoing(crypto, txid)
                    continue

                if confirmations == 0:
                    app.logger.info(
                        f"[{crypto.getname()}/{txid}] TX has no confirmations yet (entered mempool)"
                    )

                    if app.config.get("UNCONFIRMED_TX_NOTIFICATION"):
                        utx = UnconfirmedTransaction.add(
                            crypto_name, txid, addr, amount
                        )
                        send_unconfirmed_notification(utx)

                    continue

                tx = Transaction.add(
                    crypto,
                    {
                        "txid": txid,
                        "addr": addr,
                        "amount": amount,
                        "confirmations": confirmations,
                    },
                )
                tx.invoice.update_with_tx(tx)
                UnconfirmedTransaction.delete(crypto_name, txid)
                app.logger.info(f"[{crypto.getname()}/{txid}] TX has been added to db")
                if not tx.need_more_confirmations:
                    send_notification(tx)
            except sqlalchemy.exc.IntegrityError as e:
                app.logger.warning(f"[{crypto.getname()}/{txid}] TX already exist in db")
                db.session.rollback()
        return {"status": "success"}
    except NotRelatedToAnyInvoice:
        app.logger.warning(f"Transaction {txid} is not related to any invoice")
        return {
            "status": "success",
            "message": "Transaction is not related to any invoice",
        }
    except Exception as e:
        app.logger.exception(
            f"Exception while processing transaction notification: {crypto_name}/{txid}"
        )
        return {
            "status": "error",
            "message": "Exception while processing transaction notification",
            "traceback": traceback.format_exc(),
        }, 409


@blp_v1.get("/<string:crypto_name>/decrypt")
@blp_v1.response(200, DecryptResponseSchema)
@blp_v1.alt_response(403, schema=BackendKeyErrorSchema)
@blp_v1.alt_response(409, schema=ErrorSchema)
@blp_v1.doc(security=[{"BackendKey": []}])
def decrypt_key(crypto_name):
    """Return wallet encryption state (used by backend services)."""
    try:
        if "X-Shkeeper-Backend-Key" not in request.headers:
            app.logger.warning("No backend key provided")
            return {"status": "error", "message": "No backend key provided"}, 403

        bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
        if request.headers["X-Shkeeper-Backend-Key"] != bkey:
            app.logger.warning("Wrong backend key")
            return {"status": "error", "message": "Wrong backend key"}, 403

        try:
            crypto = Crypto.instances[crypto_name]
        except KeyError:
            return {
                "status": "success",
                "message": f"Ignoring notification for {crypto_name}: crypto is not available for processing",
            }

    except Exception as e:
        return {
            "status": "error",
            "message": "Exception while processing transaction notification",
            "traceback": traceback.format_exc(),
        }, 409

    return {
        "persistent_status": wallet_encryption.persistent_status().name,
        "runtime_status": wallet_encryption.runtime_status().name,
        "key": wallet_encryption.key(),
    }


@blp_v1.get("/<string:crypto_name>/server")
@blp_v1.response(200, schema=ServerDetailsResponseSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def get_server_details(crypto_name):
    """Return RPC server credentials and host."""
    crypto = Crypto.instances[crypto_name]
    usr, pwd = crypto.get_rpc_credentials()
    host = crypto.gethost()
    return {"status": "success", "key": f"{usr}:{pwd}", "host": host}


@blp_v1.post("/<string:crypto_name>/server/key")
@blp_v1.response(200, schema=ErrorSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def set_server_key(crypto_name):
    """Not implemented yet (placeholder)."""
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@blp_v1.post("/<string:crypto_name>/server/host")
@blp_v1.response(200, schema=ErrorSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def set_server_host(crypto_name):
    """Not implemented yet (placeholder)."""
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@blp_v1.get("/<string:crypto_name>/backup")
#@blp_v1.alt_response(200, fields.Raw())  # binary/streaming response
@blp_v1.doc(security=[{"basic": []}])
@login_required
def backup(crypto_name):
    """Return a wallet backup (either file content or streamed binary from a remote URL)."""
    crypto = Crypto.instances[crypto_name]
    if isinstance(crypto, (TronToken, Ethereum, Monero, BitcoinLightning)):
        filename, content = crypto.dump_wallet()
        headers = Headers()
        headers.add("Content-Type", "application/json")
        headers.add("Content-Disposition", f'attachment; filename="{filename}"')
        return Response(content, headers=headers)

    url = crypto.dump_wallet()
    bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY")
    req = requests.get(url, stream=True, headers={"X-SHKEEPER-BACKEND-KEY": bkey})
    headers = Headers()
    headers.add("Content-Type", req.headers["content-type"])
    # headers.add('Content-Disposition', req.headers['Content-Disposition'])
    fname = url.split("/")[-1]
    headers.add("Content-Disposition", f'attachment; filename="{fname}"')
    return Response(
        stream_with_context(req.iter_content(chunk_size=2048)), headers=headers
    )


@blp_v1.post("/<string:crypto_name>/exchange-rate")
@blp_v1.arguments(ExchangeRateSetRequestSchema, as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.doc(security=[{"basic": []}])
@login_required
def set_exchange_rate(crypto_name):
    """Update exchange rate source/values for a crypto/fiat pair."""
    req = request.get_json(force=True)
    rate_source = ExchangeRate.query.filter_by(
        crypto=crypto_name, fiat=req["fiat"]
    ).first()
    if not rate_source:
        return {
            "status": "error",
            "message": f"No rate configured for {crypto_name}/{req['fiat']}",
        }
    rate_source.source = req["source"]
    if rate_source.source == "manual":
        rate_source.rate = req["rate"]
    rate_source.fee = req["fee"]
    db.session.commit()
    return {"status": "success"}


@blp_v1.get("/<string:crypto_name>/estimate-tx-fee/<string:amount>")
#@blp_v1.response(200, fields.Raw())  # structure depends on crypto implementation
@blp_v1.doc(security=[{"basic": []}])
@login_required
def estimate_tx_fee(crypto_name, amount):
    """Estimate transaction fee for a given amount (optionally address via query)."""
    crypto = Crypto.instances[crypto_name]
    return crypto.estimate_tx_fee(amount, address=request.args.get("address"))


@blp_v1.get("/<string:crypto_name>/task/<string:id>")
#@blp_v1.response(200, fields.Raw())
@blp_v1.doc(security=[{"basic": []}])
@basic_auth_optional
@login_required
def get_task(crypto_name, id):
    """Get task/job details by id from crypto backend."""
    crypto = Crypto.instances[crypto_name]
    return crypto.get_task(id)


@blp_v1.post("/<string:crypto_name>/multipayout")
@blp_v1.arguments(TestCallbackSchema, as_kwargs=False)  # accept arbitrary JSON array/object
#@blp_v1.response(200, fields.Raw())
@blp_v1.response(400, schema=ErrorSchema)
@blp_v1.doc(security=[{"basic": []}])
@basic_auth_optional
@login_required
def multipayout(crypto_name):
    """Execute multi-payout with provided list of destinations and amounts."""
    try:
        payout_list = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
    except Exception as e:
        app.logger.exception("Multipayout error")
        return {"status": "error", "message": f"Error: {e}", "traceback": traceback.format_exc()}
    return crypto.multipayout(payout_list)


@blp_v1.get("/<string:crypto_name>/addresses")
@blp_v1.response(200, ListAddressesResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def list_addresses(crypto_name):
    """List all known wallet addresses for a crypto."""
    try:
        addresses = Crypto.instances[crypto_name].get_all_addresses()
        return {"status": "success", "addresses": addresses}
    except Exception as e:
        app.logger.exception(f"Failed to list addresses for {crypto_name}")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.get("/transactions", defaults={"crypto": None, "addr": None})
@blp_v1.get("/transactions/<string:crypto>/<string:addr>")
@blp_v1.response(200, TransactionsListResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def list_transactions(crypto, addr):
    """List transactions (confirmed + unconfirmed), optionally filtered by crypto/address."""
    try:
        if crypto is None or addr is None:
            transactions = (
                *Transaction.query.all(),
                *UnconfirmedTransaction.query.all(),
            )
        else:
            confirmed = (
                Transaction.query.join(Invoice)
                .join(InvoiceAddress, isouter=True)
                .filter(Transaction.crypto == crypto)
                .filter((Invoice.addr == addr) | (InvoiceAddress.addr == addr))
            )
            transactions = (
                *confirmed,
                *UnconfirmedTransaction.query.filter_by(crypto=crypto, addr=addr),
            )
        return jsonify(
            status="success", transactions=[tx.to_json() for tx in transactions]
        )
    except Exception as e:
        app.logger.exception(f"Failed to list transactions")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.get("/invoices", defaults={"external_id": None})
@blp_v1.get("/invoices/<string:external_id>")
@blp_v1.response(200, InvoicesListResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def list_invoices(external_id):
    """List invoices, optionally filtered by external_id (excluding OUTGOING)."""
    try:
        if external_id is None:
            invoices = Invoice.query.filter(Invoice.status != "OUTGOING").all()
        else:
            invoices = Invoice.query.filter_by(external_id=external_id)
        return jsonify(status="success", invoices=[i.to_json() for i in invoices])
    except Exception as e:
        app.logger.exception(f"Failed to list invoices")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.get("/<string:crypto_name>/payouts")
@blp_v1.response(200, PayoutsCheckResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def list_payouts(crypto_name):
    """Check if payouts exist for the provided amount (query param)."""
    try:
        amount = request.args.get("amount")

        if not amount:
            raise Exception("No amount provided.")

        if Payout.query.filter_by(amount=amount).all():
            return {"status": "success"}
        else:
            return {
                "status": "error",
                "message": f"No payouts for {amount} {crypto_name} found.",
            }
    except Exception as e:
        app.logger.exception(f"Failed to check payouts for {amount} {crypto_name}")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.get("/tx-info/<string:txid>/<string:external_id>")
@blp_v1.response(200, TxInfoResponseSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def get_txid_info(txid, external_id):
    """Return lightweight info for a txid bound to an external invoice id."""
    try:
        info = {}
        if (
            tx := Transaction.query.join(Invoice)
            .filter(Transaction.txid == txid, Invoice.external_id == external_id)
            .first()
        ):
            info = {
                "crypto": tx.crypto,
                "amount": format_decimal(tx.amount_fiat),
                "addr": tx.addr,
            }
        return {"status": "success", "info": info}
    except Exception as e:
        app.logger.exception(f"Failed to get transaction info for {txid}, external id: {external_id}!")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@blp_v1.post("/decryption-key")
@blp_v1.arguments(DecryptionKeyFormSchema, location="form", as_kwargs=False)
@blp_v1.response(200, SuccessSchema)
@blp_v1.alt_response(400, schema=ErrorSchema)
@with_security({"API_Key": []})
@api_key_required
def decryption_key():
    """Submit the decryption key when wallet encryption is enabled."""
    if not (key := request.form.get("key")):
        return {"status": "error", "message": "Decryption key is required"}
    if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.success:
        return {"status": "success", "message": "Decryption key was already entered"}
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        if wallet_encryption.test_key(key):
            wallet_encryption.set_key(key)
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.success)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Invalid decryption key"}
    else:
        return {"status": "error", "message": "Wallet is not encrypted"}


@blp_v1.post("/test-callback-receiver")
@blp_v1.arguments(TestCallbackSchema, as_kwargs=False)
@blp_v1.response(202, SuccessSchema)
@with_security({"API_Key": []})
@api_key_required
def test_callback_receiver():
    callback = request.get_json(force=True)
    app.logger.info("=============== Test callback received ===================")
    app.logger.info(callback)
    return {"status": "success", "message": "callback logged"}, 202
