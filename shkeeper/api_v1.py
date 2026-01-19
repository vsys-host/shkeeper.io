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
from shkeeper.services.crypto_cache import get_available_cryptos
from shkeeper.services.balance_service import get_balances


# =========================
# Marshmallow Schemas
# =========================
# TODO: schemas into separate file
class ErrorSchema(Schema):
    status = fields.String(
        example="error",
        description="Request status"
    )
    message = fields.String(
        description="Error message"
    )
    traceback = fields.String(load_default=None)

class SuccessSchema(Schema):
    status = fields.String(
        example="success",
        description="Request status"
    )

class CryptoItemSchema(Schema):
    name = fields.String(
        description="Crypto identifier used in API endpoints",
        example="ETH"
    )
    display_name = fields.String(
        description="Human-readable crypto name",
        example="Ethereum"
    )

class GetCryptoResponseSchema(Schema):
    status = fields.String(
        description="Response status",
        example="success"
    )
    crypto = fields.List(
        fields.String(),
        description="Legacy list of crypto identifiers (backward compatibility)",
        example=["BNB", "BTC", "ETH"]
    )
    crypto_list = fields.List(
        fields.Nested(CryptoItemSchema),
        description="Preferred list of available cryptocurrencies"
    )

class PaymentRequestSchema(Schema):
    external_id = fields.String(
        required=False,
        example="order_123456",
        description="External order ID in merchant system"
    )
    fiat = fields.String(
        required=True,
        example="USD",
        description="Fiat currency code (ISO 4217)"
    )
    amount = fields.String(
        required=True,
        example="100.00",
        description="Order amount in fiat currency as string"
    )
    callback_url = fields.Url(
        required=False,
        example="https://example.com/payment/callback",
        description="URL that will receive payment status callbacks"
    )

class PaymentResponseSchema(Schema):
    status = fields.String(
        example="success",
        description="Payment processing status"
    )
    amount = fields.String(
        example="0.01080125",
        description="Payment amount as a string to preserve precision"
    )
    exchange_rate = fields.String(
        example="3379.24",
        description="Exchange rate at the time of payment"
    )
    display_name = fields.String(
        example="Ethereum",
        description="Human-readable cryptocurrency name"
    )
    wallet = fields.String(
        example="0x8695f1a224e28adf362E6f8a8E695EDCc5D64960",
        description="Destination wallet address"
    )
    recalculate_after = fields.Integer(
        example=0,
        description="Seconds after which the exchange rate should be recalculated"
    )

class ErrorPaymentResponseSchema(Schema):
    status = fields.String(
        example="error",
        description="Error status"
    )
    message = fields.String(
        example="BTC payment gateway is unavailable",
        description="Human-readable error message"
    )

class BalanceItemSchema(Schema):
    name = fields.String(description="Crypto symbol", example="BTC")
    display_name = fields.String(description="Human-readable crypto name", example="Bitcoin")
    amount_crypto = fields.String(description="Amount in crypto", example="0.12345678")
    rate = fields.String(description="Current exchange rate to fiat", example="70616.07")
    fiat = fields.String(description="Fiat currency", example="USD")
    amount_fiat = fields.String(description="Amount in fiat currency", example="8700.12")
    server_status = fields.String(description="Backend node/server status", example="online")

class BalancesResponseSchema(Schema):
    status = fields.String(description="Response status", example="success")
    balances = fields.List(fields.Nested(BalanceItemSchema), description="List of balances")

class BalancesErrorSchema(Schema):
    status = fields.String(description="Response status", example="error")
    message = fields.String(description="Error message", example="No valid cryptos requested")

class QuoteRequestSchema(Schema):
    fiat = fields.String(required=True, example="USD")
    amount = fields.String(required=True, example="10.00")

class QuoteResponseSchema(Schema):
    status = fields.String(example="success")
    crypto_amount = fields.String()
    exchange_rate = fields.String()

class BalanceResponseSchema(Schema):
    name = fields.String(description="Crypto symbol", example="ETH")
    display_name = fields.String(description="Human-readable crypto name", example="Ethereum")
    amount_crypto = fields.String(description="Balance in crypto units", example="0.0213590094")
    rate = fields.String(description="Current exchange rate to fiat", example="4158.44000000")
    fiat = fields.String(description="Fiat currency", example="USD")
    amount_fiat = fields.String(description="Balance converted to fiat", example="88.8201590493")
    server_status = fields.String(description="Current status of crypto server", example="Synced")

class PayoutRequestSchema(Schema):
    amount = fields.String(required=True, description="The amount to send", example="107")
    destination = fields.String(required=True, description="Destination address", example="0xBD26e3512ce84F315e90E3FE75907bfbB5bD0c44")
    fee = fields.String(required=True, description="Transaction fee (sat/vByte for BTC, sat/Byte for LTC/DOGE, integer for XMR, ignored for others)", example="10")
    callback_url = fields.String(required=False, description="Optional callback URL to receive payout notifications", example="https://my.payout.com/notification")
    external_id = fields.String(required=False, description="Optional external order ID", example="435345534")

class PayoutResponseSchema(Schema):
    task_id = fields.String(description="ID of the payout task", example="b2a01bb0-8abe-403b-a3fa-8124c84bcf23")
    external_id = fields.String(description="Echoed external ID if provided", example="435345534")

class TaskResultItemSchema(Schema):
    dest = fields.String(description="Destination address", example="TGusXhweqkJ1aJftjmAfLqA1rfEWD4hSGZ")
    amount = fields.String(description="Amount sent", example="100")
    status = fields.String(description="Status of payout item", example="success")
    txids = fields.List(fields.String(), description="Transaction IDs associated with this payout", example=[
        "4c32969220743644e3480d96e95a423d351049ac6296b8315103225709881ae3",
        "da2996bae7a8a4d655a1288f8f4c79ce0aa3640e61f8ae8de08ae9c70c72d90d"
    ])

class TaskResponseSchema(Schema):
    result = fields.List(fields.Nested(TaskResultItemSchema), allow_none=True, description="Task results or null if pending")
    status = fields.String(required=True, description="Task status", example="PENDING / SUCCESS / FAILURE")

class MultipayoutItemSchema(Schema):
    dest = fields.String(required=True, description="Destination address", example="0xE77895BAda700d663f033510f73f1E988CF55756")
    amount = fields.String(required=True, description="Amount to send", example="100.0")
    external_id = fields.String(description="Optional external ID", example="43234")
    callback_url = fields.String(description="Optional callback URL", example="https://my.payout.com/notification")
    dest_tag = fields.Integer(description="Optional XRP destination tag", example=12345)

class MultipayoutRequestSchema(Schema):
    __root__ = fields.List(fields.Nested(MultipayoutItemSchema), required=True)

class MultipayoutResponseSchema(Schema):
    task_id = fields.String(example="0471adec-5de5-4668-bc1d-e8e7729cb676")
    external_ids = fields.List(fields.String(), example=["43234", "43235"])

class ListAddressesResponseSchema(Schema):
    status = fields.String(
        description="Response status",
        example="success"
    )
    addresses = fields.List(
        fields.String(),
        description="List of wallet addresses for the given crypto",
        example=[
            "0x0A71f4741DcaD3C06AA51eE6cF0E22675507d0d0",
            "0x8695f1a224e28adf362E6f8a8E695EDCc5D64960"
        ]
    )

class InvoiceTransactionSchema(Schema):
    txid = fields.String(description="Transaction ID")
    amount = fields.String(description="Transaction amount in crypto")
    crypto = fields.String(description="Crypto currency symbol")
    addr = fields.String(description="Crypto address")
    status = fields.String(description="Transaction status")

class InvoiceSchema(Schema):
    external_id = fields.String(description="External invoice ID")
    fiat = fields.String(description="Fiat currency code, e.g., USD")
    amount_fiat = fields.String(description="Amount in fiat")
    balance_fiat = fields.String(description="Balance in fiat")
    status = fields.String(description="Invoice status, e.g., UNPAID")
    txs = fields.List(fields.Nested(InvoiceTransactionSchema), description="Transactions linked to this invoice")


class InvoicesListResponseSchema(Schema):
    status = fields.String(required=True, example="success")
    invoices = fields.List(fields.Nested(InvoiceSchema), required=True, description="List of invoices")

class TxInfoSchema(Schema):
    addr = fields.String(
        required=True,
        description="Transaction address",
        example="0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
    )
    amount = fields.String(
        required=True,
        description="Transaction amount",
        example="0.295503",
    )
    crypto = fields.String(
        required=True,
        description="Cryptocurrency code",
        example="ETH",
    )

class TxInfoResponseSchema(Schema):
    status = fields.String(
        example="success",
    )
    info = fields.Nested(
        TxInfoSchema,
        description="Transaction info. Empty object if transaction not found.",
        example={
            "addr": "0xDCA83F12D963c7233E939a32e31aD758C7cCF307",
            "amount": "0.295503",
            "crypto": "ETH",
        },
    )

class TransactionSchema(Schema):
    addr = fields.String(
        description="Cryptocurrency address",
        example="0xDCA83F12D963c7233E939a32e31aD758C7cCF307"
    )
    amount = fields.String(
        description="Transaction amount",
        example="0.0001000000"
    )
    crypto = fields.String(
        description="Cryptocurrency symbol",
        example="ETH"
    )
    status = fields.String(
        description="Transaction status",
        example="CONFIRMED"
    )
    txid = fields.String(
        description="Transaction ID",
        example="0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66"
    )

class RetrieveTransactionsResponseSchema(Schema):
    status = fields.String(
        example="success",
        description="Request status"
    )
    transactions = fields.List(
        fields.Nested(TransactionSchema),
        description="List of transactions for the requested address"
    )

class DecryptionKeySuccessSchema(Schema):
    status = fields.String(
        example="success",
        description="Request status"
    )
    message = fields.String(
        example="Decryption key was already entered",
        description="Optional message if key was already submitted"
    )

class DecryptionKeyErrorSchema(Schema):
    status = fields.String(
        example="error",
        description="Request status"
    )
    message = fields.String(
        example="Invalid decryption key",
        description="Error message describing what went wrong"
    )

class DecryptionKeyFormSchema(Schema):
    key = fields.String(
        description="The decryption key to unlock the wallet",
        example="asdfasfasgasgasgasgdeagweg"
    )

# =========================
# smorest Blueprint
# =========================
blp_v1 = SmorestBlueprint(
    "api_v1",
    "api_v1",
    url_prefix="/api/v1",
    description="SHKeeper v1 endpoints"
)

@blp_v1.route("/crypto")
@blp_v1.doc(
    description=(
        "Retrieve the list of available cryptocurrencies.\n\n"
        "Use `crypto_list` for integrations. "
        "The `crypto` field is kept only for backward compatibility."
    ),
    tags=["Cryptos"],
    responses={
        200: {
            "description": "Success – available cryptocurrencies retrieved",
            "content": {"application/json": {"schema": GetCryptoResponseSchema}},
        }
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/crypto'\n"
                ),
            }
        ]
    },
)
def list_crypto():
    data = get_available_cryptos()
    return {
        "status": "success",
        "crypto": data["filtered"],
        "crypto_list": data["crypto_list"],
    }


@blp_v1.get("/crypto/balances")
@blp_v1.doc(
    description="Retrieve balances for all enabled cryptos, or for a subset specified via query parameter 'includes'.",
    tags=["Cryptos"],
    security=[{"API_Key": []}],
    parameters=[
        {
            "name": "includes",
            "in": "query",
            "required": False,
            "description": "Comma-separated list of crypto identifiers to return balances for (e.g., BTC,ETH,TRX)",
            "schema": {"type": "string", "example": "BTC,ETH"}
        }
    ],
    responses={
        200: {
            "description": "Success – balances retrieved",
            "content": {"application/json": {"schema": BalancesResponseSchema}}
        },
        400: {
            "description": "Error – invalid includes or no valid cryptos requested",
            "content": {"application/json": {"schema": BalancesErrorSchema}}
        },
    },
    **{
        "x-codeSamples": [
        {
            "lang": "cURL",
            "label": "CLI",
            "source": (
                "curl --location --request GET "
                "'https://demo.shkeeper.io/api/v1/crypto/balances?includes=BTC,ETH' \\\n"
                "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                "--header 'Content-Type: application/json'\n"
            ),
        }
    ]
  }
)
@api_key_required
def get_all_balances():
    includes = request.args.get("includes")
    if includes:
        includes = includes.split(",")
    else:
        includes = None
    balances, error = get_balances(includes)
    if error:
        return {"status": "error", "message": error}, 400
    return balances


@blp_v1.get("/<string:crypto_name>/generate-address")
@login_required
def generate_address(crypto_name):
    crypto = Crypto.instances[crypto_name]
    addr = crypto.mkaddr()
    return {"status": "success", "addr": addr}


@blp_v1.post("/<string:crypto_name>/payment_request")
@blp_v1.doc(
    description="Create a payment request",
    security=[{"API_Key": []}],
    tags=["Payments"],
    requestBody={
        "required": True,
        "content": {"application/json": {"schema": PaymentRequestSchema}},
    },
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": PaymentResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorPaymentResponseSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request POST "
                    "'https://demo.shkeeper.io/api/v1/ETH/payment_request' \\\n"
                    "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                    "--header 'Content-Type: application/json' \\\n"
                    "--data-raw '{\"external_id\":107,\"fiat\":\"USD\",\"amount\":\"18.25\",\"callback_url\":\"https://my-billing/callback.php\"}'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Create a quote",
    security=[{"API_Key": []}],
    tags=["Crypto"],
    requestBody={
        "required": False,
        "content": {"application/json": {"schema": QuoteRequestSchema}},
    },
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": QuoteResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request POST "
                    "'https://demo.shkeeper.io/api/v1/ETH/quote' \\\n"
                    "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                    "--header 'Content-Type: application/json' \\\n"
                    "--data-raw '{\"fiat\":\"USD\",\"amount\":\"100.00\"}'\n"
                ),
            }
        ]
    }
)
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
@login_required
def payment_gateway_set_status(crypto_name):
    """Enable/disable payment gateway."""
    req = request.get_json(force=True)
    crypto = Crypto.instances[crypto_name]
    crypto.wallet.enabled = req["enabled"]
    db.session.commit()
    return {"status": "success"}


@blp_v1.post("/<string:crypto_name>/payment-gateway/token")
@login_required
def payment_gateway_set_token(crypto_name):
    """Set shared API token for all cryptos."""
    req = request.get_json(force=True)
    for crypto in Crypto.instances.values():
        crypto.wallet.apikey = req["token"]
    db.session.commit()
    return {"status": "success"}


@blp_v1.post("/<string:crypto_name>/transaction")
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
@blp_v1.doc(
    description="Retrieve balance information for a specific crypto, including amount in crypto, fiat, and server status.",
    tags=["Cryptos"],
    security=[{"API_Key": []}],
    responses={
        200: {
            "description": "Success – balance retrieved",
            "content": {"application/json": {"schema": BalanceResponseSchema}}
        },
        400: {
            "description": "Error – crypto not enabled or invalid",
            "content": {"application/json": {"schema": ErrorSchema}}
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/ETH/balance' \\\n"
                    "--header 'X-Shkeeper-Api-Key: YOUR_API_KEY'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Create a single payout for the specified crypto.",
    tags=["Payouts"],
    security=[{"Basic_Optional": []}],
    requestBody={
        "required": True,
        "content": {"application/json": {"schema": PayoutRequestSchema}}
    },
    responses={
        200: {
            "description": "Payout task successfully created",
            "content": {"application/json": {"schema": PayoutResponseSchema}}
        },
        400: {
            "description": "Error creating payout",
            "content": {"application/json": {"schema": ErrorSchema}}
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/BTC/payout/status?external_id=abc123' \\\n"
                    "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
                ),
            }
        ]
    }
)
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
@login_required
def get_server_details(crypto_name):
    """Return RPC server credentials and host."""
    crypto = Crypto.instances[crypto_name]
    usr, pwd = crypto.get_rpc_credentials()
    host = crypto.gethost()
    return {"status": "success", "key": f"{usr}:{pwd}", "host": host}


@blp_v1.post("/<string:crypto_name>/server/key")
@login_required
def set_server_key(crypto_name):
    """Not implemented yet (placeholder)."""
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@blp_v1.post("/<string:crypto_name>/server/host")
@login_required
def set_server_host(crypto_name):
    """Not implemented yet (placeholder)."""
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@blp_v1.get("/<string:crypto_name>/backup")
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
@login_required
def estimate_tx_fee(crypto_name, amount):
    """Estimate transaction fee for a given amount (optionally address via query)."""
    crypto = Crypto.instances[crypto_name]
    return crypto.estimate_tx_fee(amount, address=request.args.get("address"))


@blp_v1.get("/<string:crypto_name>/task/<string:id>")
@blp_v1.doc(
    description="Check the status of a multi-payout task for the specified crypto.",
    tags=["Other"],
    security=[{"Basic_Optional": []}],
    responses={
        200: {
            "description": "Task status (PENDING, SUCCESS, or FAILURE)",
            "content": {
                "application/json": {"schema": TaskResponseSchema}
            },
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/ETH-USDC/task/7028c45b-0c88-483e-b703-dd455a361b2e' \\\n"
                    "--header 'Authorization: Basic YOUR_BASE64_CREDENTIALS' \\\n"
                    "--header 'Content-Type: application/json'\n"
                ),
            }
        ]
    }
)
@basic_auth_optional
@login_required
def get_task(crypto_name, id):
    """Get task/job details by id from crypto backend."""
    crypto = Crypto.instances[crypto_name]
    return crypto.get_task(id)


@blp_v1.post("/<string:crypto_name>/multipayout")
@blp_v1.doc(
    description="Execute a multi-payout for the specified crypto.",
    tags=["Payouts"],
    security=[{"Basic_Optional": []}],
    requestBody={
        "required": True,
        "content": {"application/json": {"schema": MultipayoutRequestSchema}}
    },
    responses={
        200: {"description": "Success", "content": {"application/json": {"schema": MultipayoutResponseSchema}}},
        400: {"description": "Error", "content": {"application/json": {"schema": ErrorSchema}}},
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request POST "
                    "'https://demo.shkeeper.io/api/v1/ETH-USDT/multipayout' \\\n"
                    "--header 'Authorization: Basic YOUR_BASE64_CREDENTIALS' \\\n"
                    "--header 'Content-Type: application/json' \\\n"
                    "--data-raw '["
                    "{\"dest\":\"0xE77895BAda700d663f033510f73f1E988CF55756\",\"amount\":\"100\",\"external_id\":\"43234\",\"callback_url\":\"https://my.payout.com/notification\"},"
                    "{\"dest\":\"0x7C4C7D3010d31329dd8244617C46e460E5EF8a6F\",\"amount\":\"200.11\",\"external_id\":\"43235\",\"callback_url\":\"https://my.payout.com/notification\"}"
                    "]'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Retrieve all known wallet addresses for the specified crypto.",
    security=[{"API_Key": []}],
    tags=["Transactions"],
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": ListAddressesResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/ETH-USDC/addresses' \\\n"
                    "--header 'X-Shkeeper-Api-Key: YOUR_API_KEY'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Retrieve transactions for a given crypto and address. If none provided, returns all transactions.",
    security=[{"API_Key": []}],
    tags=["Transactions"],
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": RetrieveTransactionsResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/transactions/ETH/0xDCA83F12D963c7233E939a32e31aD758C7cCF307' \\\n"
                    "--header 'X-Shkeeper-API-Key: YOUR_API_KEY'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Retrieve invoices. Optionally filter by external_id. Excludes invoices with status 'OUTGOING'.",
    security=[{"API_Key": []}],
    tags=["Invoices"],
    responses={
        200: {
            "description": "List of invoices",
            "content": {"application/json": {"schema": InvoicesListResponseSchema}},
        },
        400: {
            "description": "Error occurred",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/invoices/107' \\\n"
                    "--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Create a payout notification",
    security=[{"API_Key": []}],
    tags=["Transactions"],
    requestBody={
        "required": False,
        "content": {"application/json": {"schema": TxInfoSchema}},
    },
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": TxInfoResponseSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": ErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request GET "
                    "'https://demo.shkeeper.io/api/v1/tx-info/"
                    "0xbcf68720db79454f40b2acf6bfb18897d497ab4d8bc9faf243c859d14d5d6b66/240' \\\n"
                    "--header 'X-Shkeeper-API-Key: nApijGv8djih7ozY'\n"
                ),
            }
        ]
    }
)
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
@blp_v1.doc(
    description="Create an encryption",
    security=[{"API_Key": []}],
    tags=["Encryption"],
    requestBody={
        "required": False,
        "content": {"application/json": {"schema": DecryptionKeyFormSchema}},
    },
    responses={
        200: {
            "description": "Success",
            "content": {"application/json": {"schema": DecryptionKeySuccessSchema}},
        },
        400: {
            "description": "Error",
            "content": {"application/json": {"schema": DecryptionKeyErrorSchema}},
        },
    },
    **{
        "x-codeSamples": [
            {
                "lang": "cURL",
                "label": "CLI",
                "source": (
                    "curl --location --request POST "
                    "'https://demo.shkeeper.io/api/v1/decryption-key' \\\n"
                    "--header 'X-Shkeeper-API-Key: YOUR_API_KEY' \\\n"
                    "--form 'key=\"asdfasfasgasgasgasgdeagweg\"'\n"
                ),
            }
        ]
    }
)
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
@api_key_required
def test_callback_receiver():
    callback = request.get_json(force=True)
    app.logger.info("=============== Test callback received ===================")
    app.logger.info(callback)
    return {"status": "success", "message": "callback logged"}, 202
