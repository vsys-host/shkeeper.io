import click
from shkeeper import requests

from flask import Blueprint, json
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import *
from datetime import datetime, timedelta

bp = Blueprint("callback", __name__)

DEFAULT_CURRENCY = 'USD'


def send_unconfirmed_notification(utx: UnconfirmedTransaction):
    app.logger.info(
        f"send_unconfirmed_notification started for {utx.crypto} {utx.txid}, {utx.addr}, {utx.amount_crypto}"
    )

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
    for utx in UnconfirmedTransaction.query.filter_by(callback_confirmed=False):
        try:
            send_unconfirmed_notification(utx)
        except Exception as e:
            app.logger.exception(
                f"Exception while sending callback for UTX {utx.crypto}/{utx.txid}"
            )

    for tx in Transaction.query.filter_by(
        callback_confirmed=False, need_more_confirmations=False
    ):
        try:
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

def poll_unconfirmed_payouts():
    app.logger.info("poll_unconfirmed_payouts start")
    cutoff = datetime.utcnow() - timedelta(days=1)
    payouts = (
        Payout.query
        .filter(
            Payout.task_id.isnot(None),
            Payout.status == PayoutStatus.IN_PROGRESS,
            Payout.created_at >= cutoff
        )
        .all()
    )
    app.logger.info(f"poll_unconfirmed_payouts finished {payouts}")
    for payout in payouts:
        app.logger.info(f"poll_unconfirmed_payouts payout {payout}")
        crypto = Crypto.instances.get(payout.crypto)
        if not crypto:
            continue
        all_confirmed = False
        tx_to_notify = None
        for tx in payout.transactions:
            if not tx or not getattr(tx, "txid", None):
                app.logger.warning(f"Skipping invalid transaction {tx}")
                continue
            try:
                app.logger.info(f"poll_unconfirmed_payouts get_confirmations_by_txid {tx.txid}")
                confirmations = crypto.get_confirmations_by_txid(tx.txid)
                app.logger.info(f"poll_unconfirmed_payouts confirmations {confirmations}")
            except Exception:
                continue
            if confirmations > app.config.get("MIN_CONFIRMATION_BLOCK_FOR_PAYOUT"):
                all_confirmed = True
                if not tx_to_notify:
                    tx_to_notify = tx
        if all_confirmed:
            app.logger.info(f"poll_unconfirmed_payouts all_confirmed {payout}")
            app.logger.info(f"poll_unconfirmed_payouts tx_to_notify {tx_to_notify}")
            payout.status = PayoutStatus.SUCCESS
            payout.success = "Yes"
            if payout.callback_url and tx_to_notify and app.config.get("ENABLE_PAYOUT_CALLBACK"):
                app.logger.info(f"Notification create {tx_to_notify}")
                notification = Notification(
                    txid=tx_to_notify.txid,
                    object_id=payout.id,
                    type='Payout',
                    crypto=payout.crypto,
                    amount_crypto=payout.amount,
                    callback_url=payout.callback_url,
                )
                db.session.add(notification)
    db.session.commit()

def send_payout_callback_notifier():
    # --- Payout Notifications ---
    max_retries = app.config.get("REQUESTS_NOTIFICATION_RETRIES", 5)
    notifs_to_send = (
    Notification.query
        .filter(Notification.retries < max_retries, Notification.callback_confirmed == False)
        .all()
    )
    for notif in notifs_to_send:
        retries = notif.retries or 0
        try:
            app.logger.info(f"[PAYOUT {notif.object_id}] Sending payout notification try={retries}")
            success = send_payout_notification(notif)
            if not success:
                notif.retries = retries + 1
                db.session.commit()
                delay = (retries + 1) ** 2
                app.logger.info(f"[PAYOUT {notif.object_id}] Will retry in {delay} seconds")
        except Exception:
            notif.retries = retries + 1
            db.session.commit()
            app.logger.exception(f"Exception while sending payout callback object_id={notif.object_id}")

def send_payout_notification(notif: Notification):
    payout = Payout.query.get(notif.object_id)
    if not payout:
        notif.message = "Payout not found"
        db.session.commit()
        return False

    if notif.message:
        app.logger.warning(f"[PAYOUT {payout.id}] Skipping: previous error exists")
        return False

    tx = payout.transactions[0] if payout.transactions else None
    tx_hash = tx.txid if tx else None
    if not tx_hash:
        app.logger.info(f"[PAYOUT {payout.id}] No tx_hash yet — skipping callback")
        return False
    rate = ExchangeRate.get(DEFAULT_CURRENCY, payout.crypto).get_rate()
    amount_fiat = payout.amount * rate
    payload = {
        "payout_id": payout.id,
        "external_id": payout.external_id,
        "tx_hash": tx_hash,
        "status": "SUCCESS",
        "amount": str(payout.amount),
        "crypto": payout.crypto,
        "amount_fiat": str(amount_fiat),
        "currency_fiat": DEFAULT_CURRENCY,
        "timestamp": payout.created_at.isoformat(),
    }

    retries = getattr(notif, "retries", 0)
    wait = (retries + 1) ** 2
    app.logger.info(f"[PAYOUT {payout.id}] Sending webhook try={retries}, wait={wait}s")

    try:
        r = requests.post(
            payout.callback_url,
            json=payload,
            timeout=app.config.get("REQUESTS_NOTIFICATION_TIMEOUT", 10),
        )
    except Exception as e:
        notif.message = str(e)
        notif.retries = retries + 1
        db.session.commit()
        return False

    if r.status_code != 202:
        notif.message = f"{r.status_code} {r.reason}"
        notif.retries = retries + 1
        db.session.commit()
        return False

    # Success
    notif.callback_confirmed = True
    db.session.commit()
    app.logger.info(f"[PAYOUT {payout.id}] Webhook delivered successfully")
    return True

def poll_all_pending_payouts():
    cutoff = datetime.utcnow() - timedelta(days=1)
    app.logger.info(f"poll_all_pending_payout start")
    pending_payouts = (
        Payout.query
        .filter(
            Payout.task_id.isnot(None),
            Payout.status == PayoutStatus.IN_PROGRESS,
            Payout.created_at >= cutoff
        )
        .all()
    )
    app.logger.info(f"poll_all_pending_payout pending_payouts {pending_payouts}")
    for payout in pending_payouts:
        app.logger.info(f"poll_all_pending_payout payout {payout}")
        crypto = Crypto.instances.get(payout.crypto)
        if not crypto:
            continue
        task_response = crypto.get_task(payout.task_id)
        status = task_response.get("status")
        app.logger.info(f"poll_all_pending_payout task_response {task_response}")
        if status in ("SUCCESS", "ERROR", "FAILED", "FAILURE"):
            app.logger.info(f"update_from_task")
            app.logger.info(f"update_from_task {task_response}")
            app.logger.info(f"update_from_task {payout.task_id}")
            Payout.update_from_task(task_response, payout.task_id)
    db.session.commit()

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
