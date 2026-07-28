from collections import defaultdict
import concurrent.futures
import copy
import csv
from decimal import Decimal, InvalidOperation
import inspect
from io import StringIO
import itertools
import segno

from flask_smorest import Blueprint as SmorestBlueprint
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

from shkeeper import db
from shkeeper.auth import login_required, metrics_basic_auth
from shkeeper.wallet_encryption import (
    wallet_encryption,
    WalletEncryptionRuntimeStatus,
    WalletEncryptionPersistentStatus,
)
from .modules.classes.tron_token import TronToken
from .modules.classes.ethereum import Ethereum
from shkeeper.modules.classes.rate_source import RateSource
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import (
    FeeCalculationPolicy,
    Fiat,
    Invoice,
    InvoiceAddress,
    Payout,
    PayoutDestination,
    PayoutStatus,
    PayoutTx,
    PayoutTxStatus,
    Store,
    StoreStatus,
    StoreWallet,
    StoreWalletStatus,
    UserRole,
    Wallet,
    PayoutPolicy,
    PayoutReservePolicy,
    ExchangeRate,
    InvoiceStatus,
    Transaction,
)
from shkeeper.services.crypto_cache import get_available_cryptos
from shkeeper.services.multistore import filter_multistore_cryptos, autopayout_allowed
from shkeeper.services.store_service import (
    create_store,
    create_store_owner,
    cryptos_for_store,
    get_global_fee_collection_address,
    get_store_users,
    get_store_wallet,
    ensure_store_wallets_provisioned,
    provision_store_wallets,
    retry_provisioning,
    set_global_fee_collection_address,
    set_store_status,
    store_balances_map,
    store_wallet_balance,
    update_store,
    validate_fee_collection_address,
)
from shkeeper.services.tenancy import is_admin_user, require_admin, api_key_for_session
from shkeeper.api.schemas.api_docs import metrics_doc

prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)

bp_wallet = SmorestBlueprint("wallet", __name__)


def get_crypto_label(crypto_code: str) -> str:
    if not crypto_code:
        return ""

    for c in Crypto.instances.values():
        if crypto_code in (c.crypto, c.getname()):
            return getattr(c, "_display_name", None) or c.getname()

    return crypto_code


def store_display_name(store) -> str:
    if not store:
        return "—"
    if store.is_default:
        return f"{store.name} (default)"
    return store.name


@bp_wallet.context_processor
def inject_theme():
    user = getattr(g, "user", None)
    return {
        "theme": request.cookies.get("theme", "light"),
        "is_admin": is_admin_user(user),
        "is_store_owner": bool(user and user.role == UserRole.STORE_OWNER),
        # Autopayout is admin-only; store owners never see/configure it.
        "autopayout_disabled": not autopayout_allowed(user),
    }


def _fee_deposit_for_ui(crypto, crypto_name):
    from shkeeper.services.store_service import get_store_wallet

    store = getattr(g, "current_store", None)
    if store and isinstance(crypto, Ethereum):
        sw = get_store_wallet(store, crypto_name)
        if sw and sw.fda_address:
            return crypto.fee_deposit_account_for(
                account=sw.fda_address, fda_key=sw.fda_key
            )
    return crypto.fee_deposit_account


class CryptoUIView:
    def __init__(self, crypto, crypto_name):
        self._crypto = crypto
        self._crypto_name = crypto_name
        self.fee_deposit_account = _fee_deposit_for_ui(crypto, crypto_name)

    def __getattr__(self, item):
        return getattr(self._crypto, item)

    def balance(self):
        if isinstance(self._crypto, Ethereum):
            return self._crypto.balance_for_account(
                account=self.fee_deposit_account.addr
            )
        return self._crypto.balance()


@bp_wallet.route("/")
def index():
    return redirect(url_for("wallet.wallets"))


@bp_wallet.route("/wallets")
@login_required
def wallets():
    if is_admin_user():
        cryptos = dict(sorted(Crypto.instances.items())).values()
    else:
        store = getattr(g, "current_store", None)
        if not store:
            abort(403)
        cryptos = cryptos_for_store(store)
    return render_template("wallet/wallets.j2", cryptos=cryptos)


@bp_wallet.get("/<crypto_name>/get-rate", defaults={"fiat": "USD"})
@bp_wallet.get("/<crypto_name>/get-rate/<fiat>")
@login_required
def get_source_rate(crypto_name, fiat):
    # fiat = "USD"
    rate = ExchangeRate.get(fiat, crypto_name)
    current_rate = rate.get_rate()
    return {crypto_name: current_rate}


@bp_wallet.route("/payout/<crypto_name>")
@login_required
def payout(crypto_name):
    if not is_admin_user():
        store = getattr(g, "current_store", None)
        sw = get_store_wallet(store, crypto_name) if store else None
        if not sw or sw.status != StoreWalletStatus.READY:
            abort(404)
    else:
        sw = None
        store = getattr(g, "current_store", None)
        if store:
            sw = get_store_wallet(store, crypto_name)

    crypto_inst = Crypto.instances[crypto_name]
    crypto = CryptoUIView(crypto_inst, crypto_name)
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name)

    try:
        fee_deposit_qrcode = segno.make(str(crypto.fee_deposit_account.addr))
    except Exception as e:
        fee_deposit_qrcode = None

    tmpl = "wallet/payout.j2"
    enable_payout_callback = app.config.get("ENABLE_PAYOUT_CALLBACK")
    if isinstance(crypto_inst, TronToken):
        tmpl = "wallet/payout_tron.j2"

    if isinstance(crypto_inst, Ethereum) and crypto_name != "ETH":
        tmpl = "wallet/payout_eth.j2"

    if crypto_name in [
        "ETH",
        "BNB",
        "XRP",
        "MATIC",
        "AVAX",
        "SOL",
        "ARBETH",
        "OPETH",
        "TON",
    ]:
        tmpl = "wallet/payout_eth_coin.j2"

    if crypto_name in ["BTC", "LTC", "DOGE"]:
        tmpl = "wallet/payout_btc_coin.j2"

    if "BTC-LIGHTNING" == crypto_name:
        tmpl = "wallet/payout_btc_lightning.j2"

    cold_wallet_address = sw.cold_wallet_address if sw else None
    payout_locked_destination = None
    if not is_admin_user():
        payout_locked_destination = cold_wallet_address

    return render_template(
        tmpl,
        crypto=crypto,
        pdest=pdest,
        enable_payout_callback=enable_payout_callback,
        fee_deposit_qrcode=fee_deposit_qrcode,
        cold_wallet_address=cold_wallet_address,
        payout_locked_destination=payout_locked_destination,
    )


@bp_wallet.route("/wallet/<crypto_name>")
@login_required
def manage(crypto_name):
    crypto_inst = Crypto.instances[crypto_name]
    if not is_admin_user():
        store = getattr(g, "current_store", None)
        sw = get_store_wallet(store, crypto_name) if store else None
        if not sw or sw.status != StoreWalletStatus.READY:
            abort(404)
        crypto = CryptoUIView(crypto_inst, crypto_name)
    else:
        crypto = crypto_inst
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name).all()
    wallet = Wallet.query.filter_by(crypto=crypto_name).first()

    server_templates = [
        f"wallet/manage_server_{cls.__name__.lower()}.j2"
        for cls in crypto_inst.__class__.mro()
    ][:-2]

    def f(h):
        if not h:
            return 0, 1
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
    recalc["num"], recalc["multiplier"] = f(crypto.wallet.recalc)

    return render_template(
        "wallet/manage.j2",
        crypto=crypto,
        api_key=api_key_for_session(crypto),
        pdest=pdest,
        ppolicy=[i.value for i in PayoutPolicy],
        prespolicy=[i.value for i in PayoutReservePolicy],
        recalc=recalc,
        server_templates=server_templates,
    )


@bp_wallet.get("/rates", defaults={"fiat": "USD"})
@bp_wallet.get("/rates/<fiat>")
@login_required
def list_rates(fiat):
    currencies = Fiat.list()
    if fiat not in currencies:
        abort(404)

    cryptos = copy.deepcopy(Crypto.instances).values()
    for crypto in cryptos:
        rate = ExchangeRate.get(fiat, crypto.crypto)
        if rate.fee_policy is None:
            rate.fee_policy = FeeCalculationPolicy.PERCENT_FEE
            db.session.commit()
        crypto.rate = rate

    return render_template(
        "wallet/rates.j2",
        cryptos=cryptos,
        fiat=fiat,
        currencies=currencies,
        currency_symbols=Fiat.symbols(currencies),
        rate_providers=RateSource.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        fee_calculation_policy=FeeCalculationPolicy,
        rates_readonly=not is_admin_user(),
    )


@bp_wallet.post("/rates", defaults={"fiat": "USD"})
@bp_wallet.post("/rates/<fiat>")
@login_required
def save_rates(fiat):
    require_admin()
    if fiat not in Fiat.list():
        abort(404)

    rates = defaultdict(dict)
    for k, v in request.form.items():
        if k.startswith("rates__"):
            _, symbol, field = k.split("__")
            rates[symbol][field] = v
    for symbol, fields in rates.items():
        for k in fields:
            if k in ("rate", "fee", "fixed_fee"):
                try:
                    fields[k] = Decimal(fields[k])
                except InvalidOperation:
                    fields[k] = Decimal(0)

        # app.logger.info(fields)
        # do not save rate from dynamic rate providers
        if fields["source"] != "manual":
            del fields["rate"]

        ExchangeRate.query.filter_by(crypto=symbol, fiat=fiat).update(fields)
    db.session.commit()
    return redirect(url_for("wallet.list_rates", fiat=fiat))


@bp_wallet.get("/transactions")
@login_required
def transactions():
    if is_admin_user():
        cryptos = Crypto.instances.values()
    else:
        store = getattr(g, "current_store", None)
        if not store:
            abort(403)
        cryptos = cryptos_for_store(store)
    return render_template(
        "wallet/transactions.j2",
        cryptos=[
            {
                "value": crypto.crypto,
                "label": crypto.display_name,
            }
            for crypto in cryptos
        ],
        invoice_statuses=[status.name for status in InvoiceStatus],
    )


@bp_wallet.get("/settings")
@login_required
def settings():
    """User settings page including 2FA management"""
    user = g.user
    return render_template("wallet/settings.j2", user=user)


@bp_wallet.get("/parts/transactions")
@login_required
def parts_transactions():
    show_store = is_admin_user()
    query = Transaction.query.join(Invoice)
    if not show_store:
        query = query.filter(Invoice.store_id == g.user.store_id)

    # app.logger.info(dir(query))

    for arg in request.args:
        if hasattr(Transaction, arg):
            field = getattr(Transaction, arg)
            if isinstance(field, property):
                continue
            elif "crypto" == arg:
                query = query.filter(Transaction.crypto == request.args[arg])
            else:
                query = query.filter(field.contains(request.args[arg]))

    if "addr" in request.args:
        query = (
            query.join(Invoice)
            .join(InvoiceAddress, isouter=True)
            .filter(
                Invoice.addr.contains(request.args["addr"])
                | InvoiceAddress.addr.contains(request.args["addr"])
            )
        )

    if "invoice_amount_crypto" in request.args:
        query = query.join(Invoice).filter(
            Invoice.amount_crypto.contains(request.args["invoice_amount_crypto"])
        )

    if "status" in request.args:
        query = query.join(Invoice).filter(
            Invoice.status.contains(request.args["status"])
        )

    if "external_id" in request.args:
        query = query.join(Invoice).filter(
            Invoice.external_id.contains(request.args["external_id"])
        )

    if "from_date" in request.args:
        query = query.filter(
            Transaction.created_at >= f"{request.args['from_date']} 00:00:00",
            Transaction.created_at <= f"{request.args['to_date']} 24:00:00",
        )

    if "download" in request.args:
        if "csv" == request.args["download"]:

            def generate():
                data = StringIO()
                w = csv.writer(data)
                header = []
                if show_store:
                    header.append("Store")
                header.extend(
                    [
                        "Transaction ID",
                        "Adress",
                        "Crypto",
                        "Amount",
                        "Amount $",
                        "Status",
                        "Date",
                        "External ID",
                        "Invoice Coin",
                        "Invoice $",
                        "Invoice Date",
                    ]
                )
                w.writerow(header)
                records = query.order_by(Transaction.id.desc()).all()
                for r in records:
                    store_name = store_display_name(
                        r.invoice.store if r.invoice else None
                    )
                    if r.invoice.status.name == "OUTGOING":
                        row = [
                            r.txid,
                            r.invoice.addr,
                            r.crypto,
                            r.amount_crypto,
                            r.amount_fiat,
                            r.invoice.status.name,
                            r.created_at,
                            "",
                            "",
                            "",
                            "",
                        ]
                    else:
                        row = [
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
                        ]
                    if show_store:
                        row.insert(0, store_name)
                    w.writerow(row)
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)

            response = Response(generate(), mimetype="text/csv")
            response.headers.set(
                "Content-Disposition", "attachment", filename="transactions.csv"
            )

        return response

    pagination = query.order_by(Transaction.id.desc()).paginate(per_page=50)

    txs = pagination.items
    for tx in txs:
        tx.crypto_label = get_crypto_label(tx.crypto)
        tx.store_name = store_display_name(tx.invoice.store if tx.invoice else None)

    return render_template(
        "wallet/transactions_table.j2",
        cryptos=Crypto.instances.keys(),
        invoice_statuses=[status.name for status in InvoiceStatus],
        txs=txs,
        pagination=pagination,
        show_store=show_store,
    )


@bp_wallet.route("/payouts")
@login_required
def payouts():
    if is_admin_user():
        cryptos = Crypto.instances.values()
    else:
        store = getattr(g, "current_store", None)
        if not store:
            abort(403)
        cryptos = cryptos_for_store(store)
    return render_template(
        "wallet/payouts.j2",
        cryptos=[
            {
                "value": crypto.crypto,
                "label": crypto.display_name,
            }
            for crypto in cryptos
        ],
        payout_statuses=[status.name for status in PayoutStatus],
        payout_tx_statuses=[status.name for status in PayoutTxStatus],
    )


@bp_wallet.get("/parts/payouts")
@login_required
def parts_payouts():
    show_store = is_admin_user()
    query = Payout.query
    if not show_store:
        query = query.filter_by(store_id=g.user.store_id)

    for arg in request.args:
        if hasattr(Payout, arg):
            field = getattr(Payout, arg)
            query = query.filter(field.contains(request.args[arg]))

    if "from_date" in request.args:
        query = query.filter(
            Payout.created_at >= f"{request.args['from_date']} 00:00:00",
            Payout.created_at <= f"{request.args['to_date']} 24:00:00",
        )

    if "txid" in request.args:
        query = query.join(PayoutTx).filter(
            PayoutTx.txid.contains(request.args["txid"])
        )

    if "download" in request.args:
        if "csv" == request.args["download"]:

            def generate():
                data = StringIO()
                w = csv.writer(data)
                header = ["Date", "Destination", "Amount", "Crypto", "Tx ID"]
                if show_store:
                    header.insert(0, "Store")
                w.writerow(header)
                records = query.order_by(Payout.id.desc()).all()
                for r in records:
                    row = [
                        r.created_at,
                        r.dest_addr,
                        r.amount,
                        r.crypto,
                        " ".join([tx.txid for tx in r.transactions]),
                    ]
                    if show_store:
                        row.insert(0, store_display_name(r.store))
                    w.writerow(row)
                    yield data.getvalue()
                    data.seek(0)
                    data.truncate(0)

            response = Response(generate(), mimetype="text/csv")
            response.headers.set(
                "Content-Disposition", "attachment", filename="payouts.csv"
            )

        return response

    pagination = query.order_by(Payout.id.desc()).paginate(per_page=50)

    payouts = pagination.items
    for p in payouts:
        p.crypto_label = get_crypto_label(p.crypto)
        p.store_name = store_display_name(p.store)

    return render_template(
        "wallet/payouts_table.j2",
        payouts=payouts,
        pagination=pagination,
        show_store=show_store,
    )


@bp_wallet.route("/parts/tron-multiserver", methods=("GET", "POST"))
@login_required
def parts_tron_multiserver():
    require_admin()
    if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
        any_tron_crypto = next(cryptos)
    else:
        return "No Tron crypto found."

    if request.method == "POST":
        any_tron_crypto.multiserver_set_server(request.args["server_id"])

    servers_status = any_tron_crypto.servers_status()
    return render_template(
        "wallet/configure/tron/main__multiserver_table.j2",
        servers_status=servers_status,
    )


@bp_wallet.route("/configure/tron", methods=("GET", "POST"))
@login_required
def configure_tron():
    require_admin()
    if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
        any_tron_crypto: TronToken = next(cryptos)
    else:
        return "No Tron crypto found."

    account_info = any_tron_crypto.get_account_info()
    tron_config = any_tron_crypto.get_staking_config()

    if (
        not tron_config["fee_deposit_account"]["is_active"]
        or not tron_config["energy_delegator_account"]["is_active"]
    ):
        fee_deposit_qrcode = energy_delegator_qrcode = None
        try:
            fee_deposit_qrcode = segno.make(
                tron_config["fee_deposit_account"]["address"]
            )
            energy_delegator_qrcode = segno.make(
                tron_config["energy_delegator_account"]["address"]
            )
        except Exception:
            pass
        return render_template(
            "wallet/configure/tron/activation.j2",
            i=account_info,
            config=tron_config,
            fee_deposit_qrcode=fee_deposit_qrcode,
            energy_delegator_qrcode=energy_delegator_qrcode,
        )

    return render_template(
        "wallet/configure/tron/main.j2",
        i=account_info,
        crypto=any_tron_crypto,
        tron_config=tron_config,
    )


@bp_wallet.get("/parts/tron-staking-stake")
@login_required
def get_parts_tron_staking_stake():
    require_admin()
    # if cryptos := filter(lambda x: isinstance(x, TronToken), Crypto.instances.values()):
    #     any_tron_crypto: TronToken = next(cryptos)
    # else:
    #     return "No Tron crypto found."

    # account_info = any_tron_crypto.get_account_info()
    return render_template(
        "wallet/configure/tron/main__dialog_staking__stake.j2",
    )


@bp_wallet.post("/parts/tron-staking-stake")
@login_required
def post_parts_tron_staking_stake():
    require_admin()
    tron: TronToken = next(
        filter(lambda x: isinstance(x, TronToken), Crypto.instances.values())
    )
    stake_result = tron.stake_trx(
        request.values.get("amount_trx"), request.values.get("resource")
    )
    return render_template(
        "wallet/configure/tron/main__dialog_staking__result.j2",
        stake_result=stake_result,
    )


@bp_wallet.get("/parts/tron-staking-undelegate")
@login_required
def get_parts_tron_staking_undelegate():
    require_admin()
    recipient_address = request.values.get("to")
    bandwidth_amount = int(request.values.get("bandwidth", 0))
    energy_amount = int(request.values.get("energy", 0))

    return render_template(
        "wallet/configure/tron/main__dialog_undelegation.j2",
        recipient_address=recipient_address,
        bandwidth_amount=bandwidth_amount,
        energy_amount=energy_amount,
    )


@bp_wallet.post("/parts/tron-staking-undelegate")
@login_required
def post_parts_tron_staking_undelegate():
    require_admin()
    tron: TronToken = next(
        filter(lambda x: isinstance(x, TronToken), Crypto.instances.values())
    )
    undelegate_result = tron.undelegate_trx(
        request.values.get("to"),
        request.values.get("amount_trx"),
        request.values.get("resource"),
    )
    return render_template(
        "wallet/configure/tron/main__dialog_undelegation__result.j2",
        undelegate_result=undelegate_result,
    )


@bp_wallet.get("/metrics")
@bp_wallet.doc(**metrics_doc)
@metrics_basic_auth
def metrics():
    # Deduplicate: one metrics() call per base class; skip cryptos without metrics()
    seen = set()
    unique_cryptos = []
    for crypto in Crypto.instances.values():
        if crypto.__class__.__base__ not in seen and callable(
            getattr(crypto, "metrics", None)
        ):
            seen.add(crypto.__class__.__base__)
            unique_cryptos.append(crypto)

    # Fetch all crypto node metrics in parallel
    crypto_metrics = ""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(crypto.metrics): crypto for crypto in unique_cryptos}
        for future in concurrent.futures.as_completed(futures):
            crypto = futures[future]
            try:
                crypto_metrics += future.result()
            except Exception as e:
                app.logger.warning(f"metrics() failed for {crypto.crypto}: {e}")

    # Shkeeper metrics
    crypto_metrics += prometheus_client.generate_latest().decode()

    return _filter_metrics(crypto_metrics)


_FILTERED_METRIC_SUFFIXES = ("last_release_info", "fullnode_version_info")


def _filter_metrics(text: str) -> str:
    """Remove metric families whose name ends with any of the filtered suffixes."""
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if stripped.startswith("# HELP ") or stripped.startswith("# TYPE "):
            # "# HELP metric_name ..." or "# TYPE metric_name ..."
            parts = stripped.split(None, 3)
            metric_name = parts[2] if len(parts) >= 3 else ""
        else:
            # data line: "metric_name{labels} value" or "metric_name value"
            metric_name = stripped.split("{")[0].split()[0]
        if metric_name.endswith(_FILTERED_METRIC_SUFFIXES):
            continue
        out.append(line)
    return "".join(out)


@bp_wallet.get("/unlock")
@login_required
def show_unlock():
    if not is_admin_user():
        return redirect(url_for("wallet.wallets"))
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.pending
    ):
        return render_template(
            "wallet/unlock_setup.j2", wallet_password=wallet_encryption
        )
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.disabled
    ):
        return redirect(url_for("wallet.wallets"))
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.pending:
            # render key input form
            return render_template(
                "wallet/unlock_key_input.j2", wallet_password=wallet_encryption
            )
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.fail:
            # render key input form with invalid key error
            flash("Invalid wallet encryption password, try again.", category="warning")
            return render_template(
                "wallet/unlock_key_input.j2", wallet_password=wallet_encryption
            )
        if wallet_encryption.runtime_status() is WalletEncryptionRuntimeStatus.success:
            # render 'wallets unlocked & redirect to /wallets after 2s'
            return render_template(
                "wallet/unlock_unlocked.j2", wallet_password=wallet_encryption
            )

    app.logger.info(
        f"show_unlock wallet_encryption.persistent_status: {wallet_encryption.persistent_status()}, wallet_encryption.runtime_status: {wallet_encryption.runtime_status()}"
    )


@bp_wallet.post("/unlock")
@login_required
def process_unlock():
    require_admin()
    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.pending
    ):
        if request.form.get("encryption"):
            if not (key := request.form.get("key")):
                flash("No password provided.", "warning")
                return redirect(url_for("wallet.show_unlock"))

            if request.form.get("key") != request.form.get("key2"):
                flash(
                    "Encryption password and its confirmatios does not match.",
                    "warning",
                )
                return redirect(url_for("wallet.show_unlock"))

            if "confirmation" not in request.form:
                flash(
                    "Yoy must confirm that you saved the encryption password.",
                    "warning",
                )
                return redirect(url_for("wallet.show_unlock"))

            wallet_encryption.set_key(key)
            hash = wallet_encryption.get_hash(key)
            wallet_encryption.save_hash(hash)
            wallet_encryption.set_persistent_status(
                WalletEncryptionPersistentStatus.enabled
            )
        else:
            wallet_encryption.set_persistent_status(
                WalletEncryptionPersistentStatus.disabled
            )
        return redirect(url_for("wallet.show_unlock"))

    if (
        wallet_encryption.persistent_status()
        is WalletEncryptionPersistentStatus.enabled
    ):
        key = request.form.get("key")
        if key_matches := wallet_encryption.test_key(key):
            wallet_encryption.set_key(key)
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.success)
        else:
            wallet_encryption.set_runtime_status(WalletEncryptionRuntimeStatus.fail)
        return redirect(url_for("wallet.show_unlock"))


@bp_wallet.route("/stores")
@login_required
def stores():
    require_admin()
    stores_list = Store.query.filter(Store.status != StoreStatus.DELETED).order_by(
        Store.id
    ).all()
    enabled_cryptos = get_available_cryptos().get("filtered", [])
    multistore_cryptos = filter_multistore_cryptos(enabled_cryptos)
    store_balances = store_balances_map(stores_list, multistore_cryptos)
    global_fee_collection = {
        crypto: get_global_fee_collection_address(crypto)
        for crypto in multistore_cryptos
    }
    return render_template(
        "wallet/stores.j2",
        stores=stores_list,
        store_balances=store_balances,
        multistore_cryptos=multistore_cryptos,
        global_fee_collection=global_fee_collection,
    )


@bp_wallet.post("/stores/create")
@login_required
def stores_create():
    require_admin()
    name = request.form.get("name", "").strip()
    fee_raw = (request.form.get("platform_fee_percent") or "0").strip()
    if not name:
        flash("Store name is required", "warning")
        return redirect(url_for("wallet.stores"))
    try:
        fee = Decimal(fee_raw)
    except (InvalidOperation, TypeError):
        flash("Invalid store commission value", "warning")
        return redirect(url_for("wallet.stores"))
    create_store(name, platform_fee_percent=fee)
    flash(f"Store {name} created", "success")
    return redirect(url_for("wallet.stores"))


@bp_wallet.post("/stores/global-fee-collection")
@login_required
def stores_global_fee_collection():
    require_admin()
    enabled_cryptos = get_available_cryptos().get("filtered", [])
    cryptos = filter_multistore_cryptos(enabled_cryptos)

    validated = {}
    invoice_cryptos = []
    other_errors = []
    for crypto in cryptos:
        try:
            validated[crypto] = validate_fee_collection_address(
                crypto, request.form.get(f"fee_collection_{crypto}")
            )
        except ValueError as exc:
            msg = str(exc)
            if "not a generated invoice/hot address" in msg:
                invoice_cryptos.append(crypto)
            else:
                other_errors.append(f"{crypto}: {msg}")

    if invoice_cryptos or other_errors:
        if invoice_cryptos:
            flash(
                f"{', '.join(invoice_cryptos)}: fee collection must be an external "
                f"address or a fee-deposit (FDA) address, not a generated invoice/hot address",
                "warning",
            )
        for err in other_errors:
            flash(err, "warning")
        return redirect(url_for("wallet.stores"))

    for crypto, address in validated.items():
        set_global_fee_collection_address(crypto, address, skip_validation=True)
    flash("Global fee collection addresses saved", "success")
    return redirect(url_for("wallet.stores"))


@bp_wallet.route("/stores/<int:store_id>")
@login_required
def store_detail(store_id):
    require_admin()
    store = Store.query.get_or_404(store_id)
    ensure_store_wallets_provisioned(store)
    store_wallets = [
        sw
        for sw in StoreWallet.query.filter_by(store_id=store.id).all()
        if sw.crypto in Crypto.instances and Crypto.instances[sw.crypto].wallet.enabled
    ]
    crypto_names = [sw.crypto for sw in store_wallets]
    balances = store_balances_map([store], crypto_names).get(store.id, {})
    return render_template(
        "wallet/store_detail.j2",
        store=store,
        store_wallets=store_wallets,
        balances=balances,
        store_users=get_store_users(store),
    )


@bp_wallet.post("/stores/<int:store_id>/update")
@login_required
def store_update(store_id):
    require_admin()
    store = Store.query.get_or_404(store_id)
    try:
        update_store(
            store,
            name=request.form.get("name"),
            platform_fee_percent=request.form.get("platform_fee_percent"),
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("wallet.store_detail", store_id=store.id))
    flash("Store settings saved", "success")
    return redirect(url_for("wallet.store_detail", store_id=store.id))


@bp_wallet.post("/stores/<int:store_id>/status")
@login_required
def store_set_status(store_id):
    require_admin()
    store = Store.query.get_or_404(store_id)
    action = (request.form.get("action") or "").strip().lower()
    mapping = {
        "suspend": StoreStatus.SUSPENDED,
        "activate": StoreStatus.ACTIVE,
        "delete": StoreStatus.DELETED,
    }
    if action not in mapping:
        flash("Unknown store action", "warning")
        return redirect(url_for("wallet.store_detail", store_id=store.id))
    try:
        set_store_status(store, mapping[action])
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("wallet.store_detail", store_id=store.id))
    if action == "delete":
        flash(f"Store {store.name} deleted", "success")
        return redirect(url_for("wallet.stores"))
    flash(f"Store {store.name} is now {mapping[action].name}", "success")
    return redirect(url_for("wallet.store_detail", store_id=store.id))


@bp_wallet.post("/stores/<int:store_id>/owner")
@login_required
def store_create_owner(store_id):
    require_admin()
    store = Store.query.get_or_404(store_id)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Username and password required", "warning")
        return redirect(url_for("wallet.store_detail", store_id=store.id))
    try:
        create_store_owner(store, username, password)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("wallet.store_detail", store_id=store.id))
    flash(f"Store owner created: {username}", "success")
    return redirect(url_for("wallet.store_detail", store_id=store.id))


@bp_wallet.post("/stores/<int:store_id>/wallets/<int:wallet_id>")
@login_required
def store_wallet_update(store_id, wallet_id):
    require_admin()
    sw = StoreWallet.query.filter_by(id=wallet_id, store_id=store_id).first_or_404()
    sw.cold_wallet_address = request.form.get("cold_wallet_address") or None
    try:
        sw.fee_collection_address = validate_fee_collection_address(
            sw.crypto, request.form.get("fee_collection_address")
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("wallet.store_detail", store_id=store_id))
    override = (request.form.get("fee_percent_override") or "").strip()
    if override:
        try:
            sw.fee_percent_override = Decimal(override)
        except (InvalidOperation, TypeError):
            flash("Invalid fee % override", "warning")
            return redirect(url_for("wallet.store_detail", store_id=store_id))
    else:
        sw.fee_percent_override = None
    db.session.commit()
    flash("Wallet settings saved", "success")
    return redirect(url_for("wallet.store_detail", store_id=store_id))


@bp_wallet.post("/stores/<int:store_id>/wallets/<crypto>/retry")
@login_required
def store_wallet_retry(store_id, crypto):
    require_admin()
    store = Store.query.get_or_404(store_id)
    retry_provisioning(store, crypto)
    flash(f"Provisioning retried for {crypto}", "success")
    return redirect(url_for("wallet.store_detail", store_id=store_id))
