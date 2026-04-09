import traceback
from os import environ
from concurrent.futures import ThreadPoolExecutor
from operator import itemgetter


from werkzeug.datastructures import Headers
from flask import jsonify
from flask import request
from flask import Response
from flask import stream_with_context
from shkeeper.modules.cryptos.btc import Btc
from shkeeper.modules.cryptos.ltc import Ltc
from shkeeper.modules.cryptos.doge import Doge
from flask import current_app as app
from flask.json import JSONDecoder
from flask_sqlalchemy import sqlalchemy
from shkeeper import requests
from shkeeper.services.payout_service import PayoutService
from flask_smorest import Blueprint as SmorestBlueprint

from shkeeper import requests
from shkeeper import db
from shkeeper.auth import basic_auth_optional, login_required, api_key_required
from shkeeper.modules.classes.crypto import Crypto
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
from functools import wraps
from shkeeper.api.schemas.api_docs import (
    crypto_list_doc, crypto_balances_doc, payment_request_doc, quote_doc, 
    balance_doc, payout_doc, task_status_doc, multipayout_doc, addresses_doc,
    transactions_doc, invoices_doc, tx_info_doc, decryption_key_doc, payout_status_doc,
    transaction_callback_doc, payout_callback_doc
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


def handle_request_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            app.logger.exception("Payout error")
            return {"status": "error", "message": str(e)}, 500

    return wrapper

@blp_v1.route("/crypto")
@blp_v1.doc(**crypto_list_doc)
def list_crypto():
    data = get_available_cryptos()
    return {
        "status": "success",
        "crypto": data["filtered"],
        "crypto_list": data["crypto_list"],
    }

@blp_v1.get("/crypto/balances")
@blp_v1.doc(**crypto_balances_doc)
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
@blp_v1.doc(**payment_request_doc)
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
        if (
            app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
            and crypto.getstatus() != "Synced"
        ):
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
@blp_v1.doc(**quote_doc)
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
        if (
            app.config.get("DISABLE_CRYPTO_WHEN_LAGS")
            and crypto.getstatus() != "Synced"
        ):
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

    if req["prespolicyOption"] not in [i.value for i in PayoutReservePolicy]:
        return {"status": "error", "message": f"Unknown payout reserve policy: {req['prespolicyOption']}"}
    w = Wallet.query.filter_by(crypto=crypto_name).first()
    if autopayout_destination := req.get("add"):
        w.pdest = autopayout_destination
    if autopayout_fee := req.get("fee"):
        w.pfee = autopayout_fee
    w.ppolicy = PayoutPolicy(req["policy"])
    w.prespolicy = PayoutReservePolicy(req["prespolicyOption"])
    if w.prespolicy == PayoutReservePolicy.AMOUNT:
        w.presamount = req["prespolicyValue"]
    elif w.prespolicy == PayoutReservePolicy.PERCENT:
        w.presamount = int(req["prespolicyValue"])  # store percent as integer
    else:
        w.presamount = None
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
        "name": crypto.crypto,
        "amount": format_decimal(crypto.balance()) if crypto.balance() else 0,
        "server": crypto.getstatus(),
    }


@blp_v1.get("/<string:crypto_name>/balance")
@blp_v1.doc(**balance_doc)
@api_key_required
def balance(crypto_name):
    if crypto_name not in Crypto.instances.keys():
        return {"status": "error", "message": f"Crypto {crypto_name} is not enabled"}
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


@blp_v1.get("/<crypto_name>/payout/status")
@blp_v1.doc(**payout_status_doc)
@api_key_required
def payout_status(crypto_name):
    external_id = request.args.get("external_id")
    if not external_id:
        return {"error": "external_id is required"}, 400
    payout = Payout.query.filter_by(external_id=external_id, crypto=crypto_name).first()

    if not payout:
        return {"error": "Payout not found"}, 404
    result = {
        "id": payout.id,
        "external_id": payout.external_id,
        "crypto": payout.crypto,
        "status": payout.status.name,
        "amount": str(payout.amount),
        "destination": payout.dest_addr,
        "txid": payout.transactions[0].txid
        if payout.transactions and len(payout.transactions) > 0
        else None,
    }
    return result, 200


@blp_v1.post("/<string:crypto_name>/payout")
@blp_v1.doc(**payout_doc)
@basic_auth_optional
@login_required
@handle_request_error
def payout(crypto_name):
    """Make a single payout."""
    req = request.get_json(force=True)
    return PayoutService.single_payout(crypto_name, req)

@blp_v1.post("/payoutnotify/<string:crypto_name>")
@blp_v1.doc(**payout_callback_doc)
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
        # for p in data:
        #     Payout.add(p, crypto_name)

        return {"status": "success"}
    except Exception as e:
        app.logger.exception("Payout notify error")
        return {"status": "error", "message": f"Error: {e}", "traceback": traceback.format_exc()}


@blp_v1.route("/walletnotify/<string:crypto_name>/<string:txid>")
@blp_v1.doc(**transaction_callback_doc)
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

        tx_data_from_crypto = crypto.getaddrbytx(txid)
        app.logger.warning(tx_data_from_crypto)

        for addr, amount, confirmations, category in tx_data_from_crypto:
            try:
                if category not in ("send", "receive"):
                    app.logger.warning(
                        f"[{crypto.crypto}/{txid}] ignoring unknown category: {category}"
                    )
                    continue

                if category == "send":
                    Transaction.add_outgoing(crypto, txid)
                    continue

                if confirmations == 0:
                    app.logger.info(
                        f"[{crypto.crypto}/{txid}] TX has no confirmations yet (entered mempool)"
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
                app.logger.info(f"[{crypto.crypto}/{txid}] TX has been added to db")
                if not tx.need_more_confirmations:
                    send_notification(tx)
            except sqlalchemy.exc.IntegrityError as e:
                app.logger.warning(f"[{crypto.crypto}/{txid}] TX already exist in db")
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

        try:
            crypto = Crypto.instances[crypto_name]
            bkey = environ.get(f"SHKEEPER_BTC_BACKEND_KEY", "shkeeper")
            if request.headers["X-Shkeeper-Backend-Key"] != bkey:
                app.logger.warning("Wrong backend key")
                return {"status": "error", "message": "Wrong backend key"}, 403
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
    if isinstance(crypto, (TronToken, Ethereum, Monero, Btc, Ltc, Doge, BitcoinLightning)):
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
@blp_v1.doc(**task_status_doc)
@basic_auth_optional
@login_required
def get_task(crypto_name, id):
    """Get task/job details by id from crypto backend."""
    crypto = Crypto.instances[crypto_name]
    return crypto.get_task(id)

@blp_v1.post("/<string:crypto_name>/multipayout")
@blp_v1.doc(**multipayout_doc)
@basic_auth_optional
@login_required
@handle_request_error
def multipayout(crypto_name):
    """Execute multi-payout with provided list of destinations and amounts."""
    payout_list = request.get_json(force=True)
    return PayoutService.multiple_payout(crypto_name, payout_list)

@blp_v1.get("/<string:crypto_name>/addresses")
@blp_v1.doc(**addresses_doc)
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
@blp_v1.doc(**transactions_doc)
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
@blp_v1.doc(**invoices_doc)
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
@blp_v1.doc(**tx_info_doc)
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
@blp_v1.doc(**decryption_key_doc)
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
