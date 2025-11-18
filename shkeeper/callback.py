import click
from shkeeper import requests

from flask import Blueprint, json
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import *


bp = Blueprint("callback", __name__)


def send_unconfirmed_notification(utx: UnconfirmedTransaction):
    app.logger.info(
        f"send_unconfirmed_notification started for {utx.crypto} {utx.txid}, {utx.addr}, {utx.amount_crypto}"
    )
    
    if utx == Notification:
      invoice = Notification
    else:    
        invoice_address = InvoiceAddress.query.filter_by(
            crypto=utx.crypto, addr=utx.addr
        ).first()
        invoice = Invoice.query.filter_by(id=invoice_address.invoice_id).first()
    crypto = Crypto.instances[utx.crypto]
    apikey = crypto.wallet.apikey

    notification = {
        "status": "unconfirmed",
        "external_id": invoice.external_id,
        "crypto": utx.crypto,
        "addr": utx.addr,
        "txid": utx.txid,
        "amount": format_decimal(utx.amount_crypto, precision=crypto.precision),
    }

    app.logger.warning(
        f"[{utx.crypto}/{utx.txid}] Posting {notification} to {invoice.callback_url} with api key {apikey}"
    )
    try:
        r = requests.post(
            invoice.callback_url,
            json=notification,
            headers={"X-Shkeeper-Api-Key": apikey},
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT"),
        )
    except Exception as e:
        app.logger.error(
            f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification failed: {e}"
        )
        return False

    if r.status_code != 202:
        app.logger.warning(
            f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification failed with HTTP code {r.status_code}"
        )
        return False

    utx.callback_confirmed = True
    db.session.commit()
    app.logger.info(
        f"[{utx.crypto}/{utx.txid}] Unconfirmed TX notification has been accepted"
    )

    return True


def send_notification(tx):
    app.logger.info(f"[{tx.crypto}/{tx.txid}] Notificator started")

    transactions = []
    for t in tx.invoice.transactions:
        amount_fiat_without_fee = t.rate.get_orig_amount(t.amount_fiat)
        transactions.append(
            {
                "txid": t.txid,
                "date": str(t.created_at),
                "amount_crypto": remove_exponent(t.amount_crypto),
                "amount_fiat": remove_exponent(t.amount_fiat),
                "amount_fiat_without_fee": remove_exponent(amount_fiat_without_fee),
                "fee_fiat": remove_exponent(t.amount_fiat - amount_fiat_without_fee),
                "trigger": tx.id == t.id,
                "crypto": t.crypto,
            }
        )

    notification = {
        "external_id": tx.invoice.external_id,
        "crypto": tx.invoice.crypto,
        "addr": tx.invoice.addr,
        "fiat": tx.invoice.fiat,
        "balance_fiat": remove_exponent(tx.invoice.balance_fiat),
        "balance_crypto": remove_exponent(tx.invoice.balance_crypto),
        "paid": tx.invoice.status in (InvoiceStatus.PAID, InvoiceStatus.OVERPAID),
        "status": tx.invoice.status.name,
        "transactions": transactions,
        "fee_percent": remove_exponent(tx.invoice.rate.fee),
        "fee_fixed": remove_exponent(tx.invoice.rate.fixed_fee),
        "fee_policy": (
            tx.invoice.rate.fee_policy.name
            if tx.invoice.rate.fee_policy
            else FeeCalculationPolicy.PERCENT_FEE.name
        ),
    }

    overpaid_fiat = tx.invoice.balance_fiat - (
        tx.invoice.amount_fiat * (tx.invoice.wallet.ulimit / 100)
    )
    notification["overpaid_fiat"] = (
        str(round(overpaid_fiat.normalize(), 2)) if overpaid_fiat > 0 else "0.00"
    )

    apikey = Crypto.instances[tx.crypto].wallet.apikey
    app.logger.warning(
        f"[{tx.crypto}/{tx.txid}] Posting {json.dumps(notification)} to {tx.invoice.callback_url} with api key {apikey}"
    )
    try:
        r = requests.post(
            tx.invoice.callback_url,
            json=notification,
            headers={"X-Shkeeper-Api-Key": apikey},
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT"),
        )
    except Exception as e:
        app.logger.error(f"[{tx.crypto}/{tx.txid}] Notification failed: {e}")
        return False

    if r.status_code != 202:
        app.logger.warning(
            f"[{tx.crypto}/{tx.txid}] Notification failed by {tx.invoice.callback_url} with HTTP code {r.status_code}"
        )
        return False

    tx.callback_confirmed = True
    db.session.commit()
    app.logger.info(
        f"[{tx.crypto}/{tx.txid}] Notification has been accepted by {tx.invoice.callback_url}"
    )
    return True


def list_unconfirmed():
    for tx in Transaction.query.filter_by(callback_confirmed=False):
        print(tx)
    else:
        print("No unconfirmed transactions found!")

def send_callbacks():
    for notif in Notification.query.filter_by(callback_confirmed=False, type="Payout"):
        try:
            app.logger.info("send send_payout_notification")
            app.logger.info(f"send send_payout_notification {notif}")
            send_payout_notification(notif)
        except Exception:
            app.logger.exception(
                f"Exception while sending payout callback object_id={notif.object_id}"
            )
    app.logger.info(f"send UnconfirmedTransaction")
    for utx in UnconfirmedTransaction.query.filter_by(callback_confirmed=False):
        try:
            app.logger.info(f"send send_unconfirmed_notification {utx}")
            send_unconfirmed_notification(utx)
        except Exception as e:
            app.logger.exception(
                f"Exception while sending callback for UTX {utx.crypto}/{utx.txid}"
            )

    for tx in Transaction.query.filter_by(
        callback_confirmed=False, need_more_confirmations=False
    ):
        try:
            app.logger.info(f"send delay_until_date")
            app.logger.info(f"send Transaction {tx}")
            delay_until_date = tx.created_at + timedelta(
                seconds=app.config.get("NOTIFICATION_TASK_DELAY")
            )
            if datetime.now() > delay_until_date:
                app.logger.info(
                    f"[{tx.crypto}/{tx.txid}] created at {tx.created_at}, delayed until {delay_until_date}"
                )
                if tx.invoice.status == InvoiceStatus.OUTGOING:
                    tx.callback_confirmed = True
                    db.session.commit()
                else:
                    app.logger.info(f"[{tx.crypto}/{tx.txid}] Notification is pending")
                    send_notification(tx)
            else:
                app.logger.info(
                    f"[{tx.crypto}/{tx.txid}] delaying notification created at {tx.created_at} until {delay_until_date}"
                )
        except Exception as e:
            app.logger.exception(
                f"Exception while sending callback for TX {tx.crypto}/{tx.txid}"
            )

def send_payout_notification(notif: Notification):
    payout = Payout.query.get(notif.object_id)
    if not payout:
        notif.message = "Payout not found"
        db.session.commit()
        return False

    if notif.message:
        app.logger.warning(f"Payout {payout.id} skipping: message already set")
        return False

    # only success status triggers callback
    if payout.status != PayoutStatus.SUCCESS:
        app.logger.info(f"Payout {payout.id} not SUCCESS, skipping")
        return False

    # build payload
    tx = payout.transactions[0] if payout.transactions else None
    tx_hash = tx.txid if tx else None

    payload = {
        "payout_id": payout.id,
        "externalId": payout.id,
        "tx_hash": tx_hash,
        "status": "SUCCESS",
        "amount": str(payout.amount),
        "currency": payout.crypto,
        "amount_fiat": str(payout.amount),
        "currency_fiat": "USD",
        "timestamp": payout.created_at.isoformat(),
    }

    # retry counter stored inside Notification
    retries = getattr(notif, "retries", 0)

    wait = (retries + 1) ** 2

    app.logger.info(
        f"[PAYOUT {payout.id}] Sending callback try={retries}, wait={wait} seconds"
    )

    try:
        r = requests.post(
            payout.callback_url,
            json=payload,
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT"),
        )
    except Exception as e:
        notif.message = str(e)
        notif.retries = retries + 1
        db.session.commit()
        return False

    if r.status_code != 200:
        notif.message = f"{r.status_code} {r.reason}"
        notif.retries = retries + 1
        db.session.commit()
        return False

    # SUCCESS
    notif.callback_confirmed = True
    notif.message = None
    db.session.commit()
    return True

def update_confirmations():
    for tx in Transaction.query.filter_by(
        callback_confirmed=False, need_more_confirmations=True
    ):
        try:
            app.logger.info(f"[{tx.crypto}/{tx.txid}] Updating confirmations")
            if not tx.is_more_confirmations_needed():
                app.logger.info(f"[{tx.crypto}/{tx.txid}] Got enough confirmations")
            else:
                app.logger.info(f"[{tx.crypto}/{tx.txid}] Not enough confirmations yet")
        except Exception as e:
            app.logger.exception(
                f"Exception while updating tx confirmations for {tx.crypto}/{tx.txid}"
            )


@bp.cli.command()
def list():
    """Shows list of transaction notifications to be sent"""
    list_unconfirmed()


@bp.cli.command()
def send():
    """Send transaction notification"""
    send_callbacks()


@bp.cli.command()
def update():
    """Update number of confirmation"""
    update_confirmations()


@bp.cli.command()
@click.option("-c", "--confirmations", default=1)
def add(confirmations):
    import time

    crypto = Crypto.instances["BTC"]
    invoice = Invoice.add(
        crypto,
        {
            "external_id": str(time.time()),
            "fiat": "USD",
            "amount": 1000,
            "callback_url": "http://localhost:5000/api/v1/wp_callback",
        },
    )
    tx = Transaction.add(
        crypto,
        {
            "txid": invoice.id * 100,
            "addr": invoice.addr,
            "amount": invoice.amount_crypto,
            "confirmations": confirmations,
        },
    )
