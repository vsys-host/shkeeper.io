from decimal import Decimal
import traceback
from os import environ

from werkzeug.datastructures import Headers
from flask import Blueprint, jsonify
from flask import request
from flask import Response
from flask import stream_with_context
from flask import current_app as app
# from flask.json import JSONDecoder
from flask_sqlalchemy import sqlalchemy
from shkeeper import requests

from shkeeper import db
from shkeeper.auth import basic_auth_optional, login_required, api_key_required
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.tron_token import TronToken
from shkeeper.modules.classes.ethereum import Ethereum
from shkeeper.modules.cryptos.bitcoin_lightning import BitcoinLightning
from shkeeper.modules.cryptos.monero import Monero
from shkeeper.modules.rates import RateSource
from shkeeper.models import *
from shkeeper.callback import send_notification, send_unconfirmed_notification
from shkeeper.utils import format_decimal
from shkeeper.wallet_encryption import (
    wallet_encryption,
    WalletEncryptionPersistentStatus,
    WalletEncryptionRuntimeStatus,
)
from shkeeper.exceptions import NotRelatedToAnyInvoice


bp = Blueprint("api_v1", __name__, url_prefix="/api/v1/")

# class DecimalJSONDecoder(JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, parse_float=Decimal, **kwargs)

# bp.json_decoder = DecimalJSONDecoder


@bp.route("/crypto")
def list_crypto():
    filtered_list = []
    crypto_list = []
    for crypto in Crypto.instances.values():
        if crypto.wallet.enabled and (crypto.getstatus() != "Offline"):
            if (not app.config.get("DISABLE_CRYPTO_WHEN_LAGS") or 
                    (app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() == "Synced")):
                filtered_list.append(crypto.crypto)
                crypto_list.append(
                    {"name": crypto.crypto, "display_name": crypto.display_name}
                )
    return {
        "status": "success",
        "crypto": filtered_list,
        "crypto_list": crypto_list,
    }


@bp.get("/<crypto_name>/generate-address")
@login_required
def generate_address(crypto_name):
    crypto = Crypto.instances[crypto_name]
    if crypto.only_read_mode() and not crypto.wallet.xpub:
        return {
            "status": "error",
            "message": f"{crypto_name} xpub should be added in read-only mode",
        }

    addr = crypto.mkaddr()
    return {"status": "success", "addr": addr}


@bp.post("/<crypto_name>/payment_request")
@api_key_required
def payment_request(crypto_name):
    try:
        crypto = Crypto.instances.get(crypto_name)
        error = None

        if not crypto or not crypto.wallet.enabled:
            error = f"{crypto_name} payment gateway is unavailable"
        elif app.config.get("DISABLE_CRYPTO_WHEN_LAGS") and crypto.getstatus() != "Synced":
            error = f"{crypto_name} payment gateway is unavailable because of lagging"
        elif crypto.only_read_mode() and not crypto.wallet.xpub:
            error = f"{crypto_name} xpub should be added in read-only mode"
        if error:
            return {"status": "error", "message": error}

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

@bp.post("/<crypto_name>/quote")
@api_key_required
def get_crypto_quote(crypto_name):
    try:
        crypto = Crypto.instances.get(crypto_name)

        if not crypto or not crypto.wallet.enabled:
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

@bp.get("/<crypto_name>/payment-gateway")
@login_required
def payment_gateway_get_status(crypto_name):
    crypto = Crypto.instances[crypto_name]
    return {
        "status": "success",
        "enabled": crypto.wallet.enabled,
        "token": crypto.wallet.apikey,
    }


@bp.post("/<crypto_name>/payment-gateway")
@login_required
def payment_gateway_set_status(crypto_name):
    req = request.get_json(force=True)
    crypto = Crypto.instances[crypto_name]
    crypto.wallet.enabled = req["enabled"]
    db.session.commit()
    return {"status": "success"}


@bp.post("/<crypto_name>/payment-gateway/token")
@login_required
def payment_gateway_set_token(crypto_name):
    req = request.get_json(force=True)
    for crypto in Crypto.instances.values():
        crypto.wallet.apikey = req["token"]
    db.session.commit()
    return {"status": "success"}


@bp.post("/<crypto_name>/transaction")
@login_required
def add_transaction(crypto_name):
    try:
        tx = request.get_json(force=True)
        # app.logger.warning(type(r['amount']))
        # app.logger.warning(Decimal(r['amount']))

        crypto = Crypto.instances[crypto_name]
        t = Transaction.add(crypto, tx)

        response = {
            "status": "success",
            "id": t.id,
        }

    except Exception as e:
        raise e
        response = {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }

    return response


@bp.post("/<crypto_name>/payout_destinations")
@login_required
def payout_destinations(crypto_name):
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


@bp.post("/<crypto_name>/autopayout")
@login_required
def autopayout(crypto_name):
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
    w.xpub = req["xPub"]
    w.recalc = req["recalc"]

    db.session.commit()
    return {"status": "success"}


@bp.get("/<crypto_name>/status")
@login_required
def status(crypto_name):
    crypto = Crypto.instances[crypto_name]
    return {
        "name": crypto.crypto,
        "amount": format_decimal(crypto.balance()) if crypto.balance() else 0,
        "server": crypto.getstatus(),
    }


@bp.post("/<crypto_name>/payout")
@basic_auth_optional
@login_required
def payout(crypto_name):
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
        return {"status": "error", "message": f"Error: {e}"}

    if "result" in res and res["result"]:
        idtxs = res["result"] if isinstance(res["result"], list) else [res["result"]]
        Payout.add(
            {"dest": req["destination"], "amount": amount, "txids": idtxs}, crypto_name
        )

    return res


@bp.post("/payoutnotify/<crypto_name>")
def payoutnotify(crypto_name):
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
        return {"status": "error", "message": f"Error: {e}"}


@bp.post("/walletnotify/<crypto_name>/<txid>")
def walletnotify(crypto_name, txid):
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
            "message": f"Exception while processing transaction notification: {traceback.format_exc()}.",
        }, 409


@bp.get("/<crypto_name>/decrypt")
def decrypt_key(crypto_name):
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
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception while processing transaction notification: {traceback.format_exc()}.",
        }, 409

    return {
        "persistent_status": wallet_encryption.persistent_status().name,
        "runtime_status": wallet_encryption.runtime_status().name,
        "key": wallet_encryption.key(),
    }


@bp.get("/<crypto_name>/server")
@login_required
def get_server_details(crypto_name):
    crypto = Crypto.instances[crypto_name]
    usr, pwd = crypto.get_rpc_credentials()
    host = crypto.gethost()
    return {"status": "success", "key": f"{usr}:{pwd}", "host": host}


@bp.post("/<crypto_name>/server/key")
@login_required
def set_server_key(crypto_name):
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@bp.post("/<crypto_name>/server/host")
@login_required
def set_server_host(crypto_name):
    # TODO: implement
    return {"status": "error", "message": "not implemented yet"}


@bp.get("/<crypto_name>/backup")
@login_required
def backup(crypto_name):
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


@bp.post("/<crypto_name>/exchange-rate")
@login_required
def set_exchange_rate(crypto_name):
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


@bp.get("/<crypto_name>/estimate-tx-fee/<amount>")
@login_required
def estimate_tx_fee(crypto_name, amount):
    crypto = Crypto.instances[crypto_name]
    return crypto.estimate_tx_fee(amount, address=request.args.get("address"))


@bp.get("/<crypto_name>/task/<id>")
@basic_auth_optional
@login_required
def get_task(crypto_name, id):
    crypto = Crypto.instances[crypto_name]
    return crypto.get_task(id)


@bp.post("/<crypto_name>/multipayout")
@basic_auth_optional
@login_required
def multipayout(crypto_name):
    try:
        payout_list = request.get_json(force=True)
        crypto = Crypto.instances[crypto_name]
    except Exception as e:
        app.logger.exception("Multipayout error")
        return {"status": "error", "message": f"Error: {e}"}
    return crypto.multipayout(payout_list)


@bp.get("/<crypto_name>/addresses")
@api_key_required
def list_addresses(crypto_name):
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


@bp.get("/transactions", defaults={"crypto": None, "addr": None})
@bp.get("/transactions/<crypto>/<addr>")
@api_key_required
def list_transactions(crypto, addr):
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


@bp.get("/invoices", defaults={"external_id": None})
@bp.get("/invoices/<external_id>")
@api_key_required
def list_invoices(external_id):
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


@bp.get("/<crypto_name>/payouts")
@api_key_required
def list_payouts(crypto_name):
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


@bp.get("/tx-info/<txid>/<external_id>")
@api_key_required
def get_txid_info(txid, external_id):
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
        app.logger.exception(f"Oops!")
        return {
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        }


@bp.post("/decryption-key")
@api_key_required
def decryption_key():
    if not (key := request.form.get("key")):
        return {"status": "error", "message": "Decryption key is requred"}
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


@bp.post("/test-callback-receiver")
@api_key_required
def test_callback_receiver():
    callback = request.get_json(force=True)
    app.logger.info("=============== Test callback received ===================")
    app.logger.info(callback)
    return {"status": "success", "message": "callback logged"}, 202
