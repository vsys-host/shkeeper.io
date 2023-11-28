import copy
import csv
import inspect
from io import StringIO
import itertools

from flask import Blueprint
from flask import flash
from flask import g
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from werkzeug.exceptions import abort
from werkzeug.wrappers import Response
from flask import current_app as app
import prometheus_client

from shkeeper.auth import login_required, metrics_basic_auth
from shkeeper.wallet_encryption import wallet_encryption, WalletEncryptionRuntimeStatus, WalletEncryptionPersistentStatus
from .modules.classes.tron_token import TronToken
from .modules.classes.ethereum import Ethereum
from shkeeper.modules.rates import RateSource
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import (
    Invoice,
    InvoiceAddress,
    Payout,
    PayoutDestination,
    PayoutStatus,
    PayoutTx,
    PayoutTxStatus,
    Wallet,
    PayoutPolicy,
    ExchangeRate,
    InvoiceStatus,
    Transaction,
)


prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

bp = Blueprint("wallet", __name__)

@bp.context_processor
def inject_theme():
    return {'theme': request.cookies.get('theme', 'light')}

@bp.route("/")
def index():
    return redirect(url_for("wallet.wallets"))

@bp.route("/wallets")
@login_required
def wallets():
    cryptos = dict(sorted(Crypto.instances.items())).values()
    return render_template("wallet/wallets.j2", cryptos=cryptos)

@bp.route("/payout/<crypto_name>")
@login_required
def payout(crypto_name):
    crypto = Crypto.instances[crypto_name]
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name)

    tmpl = "wallet/payout.j2"
    if isinstance(crypto, TronToken):
        tmpl = "wallet/payout_tron.j2"

    if isinstance(crypto, Ethereum) and crypto_name != "ETH":
        tmpl = "wallet/payout_eth.j2"

    if crypto_name == "ETH" or crypto_name == "BNB":
        tmpl = "wallet/payout_eth_coin.j2"

    return render_template(tmpl, crypto=crypto, pdest=pdest)

@bp.route("/wallet/<crypto_name>")
@login_required
def manage(crypto_name):
    crypto = Crypto.instances[crypto_name]
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name).all()
    wallet = Wallet.query.filter_by(crypto=crypto_name).first()

    server_templates = [f"wallet/manage_server_{cls.__name__.lower()}.j2" for cls in crypto.__class__.mro()][:-2]

    if not app.config['TRON_MULTISERVER_GUI']:
        server_templates = filter(lambda x: 'trontoken' not in x, server_templates)

    def f(h):
        if not h: return 0, 1
        for period in [24 * 7, 24, 1]:
            if h % period == 0:
                return int(h / period), period
    recalc = {
      "periods": [
        {"name": "Hours", "hours": 1},
        {"name": "Days", "hours": 1 * 24},
        {"name": "Weeks", "hours": 1 * 24 * 7},
      ]
    }
    recalc['num'], recalc['multiplier'] = f(crypto.wallet.recalc)

    return render_template("wallet/manage.j2",
        crypto=crypto, pdest=pdest, ppolicy=[i.value for i in PayoutPolicy], recalc=recalc, server_templates=server_templates)


@bp.route('/rates', defaults={'fiat': 'USD'})
@bp.route('/rates/<fiat>')
@login_required
def rates(fiat):
    cryptos = copy.deepcopy(Crypto.instances).values()
    for crypto in cryptos:
        crypto.rate = ExchangeRate.get(fiat, crypto.crypto)
    return render_template("wallet/rates.j2",
        cryptos=cryptos,
        fiat=fiat,
        rate_providers=RateSource.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        txs=Transaction.query.all()
    )

@bp.get('/transactions')
@login_required
def transactions():
    return render_template("wallet/transactions.j2",
        cryptos=Crypto.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
    )

@bp.get('/parts/transactions')
@login_required
def parts_transactions():
    query = Transaction.query

    # app.logger.info(dir(query))

    for arg in request.args:
        if hasattr(Transaction, arg):
            field = getattr(Transaction, arg)
            if isinstance(field, property):
                continue
            else:
                query = query.filter(field.contains(request.args[arg]))

    if 'addr' in request.args:
        query = query.join(Invoice) \
                     .join(InvoiceAddress, isouter=True) \
                     .filter(Invoice.addr.contains(request.args['addr']) | InvoiceAddress.addr.contains(request.args['addr']))

    if 'invoice_amount_crypto' in request.args:
        query = query.join(Invoice).filter(Invoice.amount_crypto.contains(request.args['invoice_amount_crypto']))

    if 'status' in request.args:
        query = query.join(Invoice).filter(Invoice.status.contains(request.args['status']))

    if 'external_id' in request.args:
        query = query.join(Invoice).filter(Invoice.external_id.contains(request.args['external_id']))

    if 'from_date' in request.args:
        query = query.filter(Transaction.created_at >= f"{request.args['from_date']} 00:00:00" , Transaction.created_at <= f"{request.args['to_date']} 24:00:00")

    if 'download' in request.args:
        if 'csv' == request.args['download']:
            def generate():
                data = StringIO()
                w = csv.writer(data)
                w.writerow(['Transaction ID','Adress','Crypto','Amount','Amount $','Status','Date','External ID','Invoice Coin','Invoice $','Invoice Date'])
                records = query.order_by(Transaction.id.desc()).all()
                for r in records:
                    if r.invoice.status.name == "OUTGOING":
                        w.writerow([
                            r.txid,
                            r.invoice.addr,
                            r.crypto,
                            r.amount_crypto,
                            r.amount_fiat,
                            r.invoice.status.name,
                            r.created_at,
                            '',
                            '',
                            '',
                            '',
                        ])
                    else:
                        w.writerow([
                            r.txid,
                            r.invoice.addr,
                            r.crypto,
                            r.amount_crypto,
                            r.amount_fiat,
                            r.invoice.status.name,
                            r.created_at,
                            r.invoice.external_id,
                            r.invoice.amount_crypto,
                            r.invoice.amount_fiat,
                            r.invoice.created_at,
                        ])
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)
            response = Response(generate(), mimetype='text/csv')
            response.headers.set("Content-Disposition", "attachment", filename="transactions.csv")

        return response

    pagination = query.order_by(Transaction.id.desc()).paginate(per_page=50)
    return render_template("wallet/transactions_table.j2",
        cryptos=Crypto.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        txs=pagination.items,
        pagination=pagination,
    )

@bp.route("/payouts")
@login_required
def payouts():
    return render_template("wallet/payouts.j2",
        cryptos=Crypto.instances.keys(),
        payout_statuses=[status.name for status in PayoutStatus],
        payout_tx_statuses=[status.name for status in PayoutTxStatus],
    )

@bp.get('/parts/payouts')
@login_required
def parts_payouts():
    query = Payout.query

    for arg in request.args:
        if hasattr(Payout, arg):
            field = getattr(Payout, arg)
            query = query.filter(field.contains(request.args[arg]))

    if 'from_date' in request.args:
        query = query.filter(Payout.created_at >= f"{request.args['from_date']} 00:00:00", Payout.created_at <= f"{request.args['to_date']} 24:00:00")

    if 'txid' in request.args:
        query = query.join(PayoutTx).filter(PayoutTx.txid.contains(request.args['txid']))

    if 'download' in request.args:
        if 'csv' == request.args['download']:
            def generate():
                data = StringIO()
                w = csv.writer(data)
                w.writerow(['Date', 'Destination', 'Amount', 'Crypto', 'Tx ID'])
                records = query.order_by(Payout.id.desc()).all()
                for r in records:
                    w.writerow([r.created_at, r.dest_addr, r.amount, r.crypto, ' '.join([tx.txid for tx in r.transactions])])
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)
            response = Response(generate(), mimetype='text/csv')
            response.headers.set("Content-Disposition", "attachment", filename="payouts.csv")

        return response

    pagination = query.order_by(Payout.id.desc()).paginate(per_page=50)
    return render_template("wallet/payouts_table.j2",
        payouts=pagination.items,
        pagination=pagination,
    )

@bp.route('/parts/tron-multiserver', methods=("GET", "POST"))
@login_required
def parts_tron_multiserver():
    if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
        any_tron_crypto = next(cryptos)
    else:
        return "No Tron crypto found."

    if request.method == 'POST':
        any_tron_crypto.multiserver_set_server(request.args['server_id'])

    servers_status = any_tron_crypto.servers_status()
    return render_template("wallet/manage_server_trontoken_status.j2", servers_status=servers_status)

@bp.get('/metrics')
@metrics_basic_auth
def metrics():

    metrics = ''

    # Crypto metrics
    seen = set()
    for crypto in Crypto.instances.values():
        if crypto.__class__.__base__ not in seen:
            try:
                metrics += crypto.metrics()
                seen.add(crypto.__class__.__base__)
            except AttributeError:
                continue

    # Shkeeper metrics
    metrics += prometheus_client.generate_latest().decode()

    return metrics

@bp.get("/unlock")
@login_required
def show_unlock():
    if wallet_encryption.persistent_status() is WalletEncryptionPersistentStatus.pending:
        return render_template("wallet/unlock_setup.j2", wallet_password=wallet_encryption)
    if wallet_encryption.persistent_status() is WalletEncryptionPersistentStatus.disabled:
        return redirect(url_for("wallet.wallets"))
    if wallet_encryption.persistent_status() is WalletEncryptionPersistentStatus.enabled:

        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.pending:
            # render key input form
            return render_template("wallet/unlock_key_input.j2", wallet_password=wallet_encryption)
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.fail:
            # render key input form with invalid key error
            flash('Invalid wallet encryption password, try again.', category='warning')
            return render_template("wallet/unlock_key_input.j2", wallet_password=wallet_encryption)
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.success:
            # render 'wallets unlocked & redirect to /wallets after 2s'
            return render_template("wallet/unlock_unlocked.j2", wallet_password=wallet_encryption)

    app.logger.info(f"show_unlock wallet_encryption.persistent_status: {wallet_encryption.persistent_status()}, wallet_encryption.runtime_status: {wallet_encryption.runtime_status()}")

@bp.post("/unlock")
@login_required
def process_unlock():
    if wallet_encryption.persistent_status() is WalletEncryptionPersistentStatus.pending:
        if request.form.get('encryption'):

            if not (key := request.form.get('key')):
                flash('No password provided.', 'warning')
                return redirect(url_for("wallet.show_unlock"))

            if request.form.get('key') != request.form.get('key2'):
                flash('Encryption password and its confirmatios does not match.', 'warning')
                return redirect(url_for("wallet.show_unlock"))

            if 'confirmation' not in request.form:
                flash('Yoy must confirm that you saved the encryption password.', 'warning')
                return redirect(url_for("wallet.show_unlock"))

            wallet_encryption.set_key(key)
            hash = wallet_encryption.get_hash(key)
            wallet_encryption.save_hash(hash)
            wallet_encryption.set_persistent_status(WalletEncryptionPersistentStatus.enabled)
        else:
            wallet_encryption.set_persistent_status(WalletEncryptionPersistentStatus.disabled)
        return redirect(url_for("wallet.show_unlock"))

    if wallet_encryption.persistent_status() is WalletEncryptionPersistentStatus.enabled:
        key = request.form.get('key')
        if key_matches := wallet_encryption.test_key(key):
            wallet_encryption.set_key(key)
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.success)
        else:
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.fail)
        return redirect(url_for("wallet.show_unlock"))