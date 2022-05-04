import copy

from flask import Blueprint
from flask import flash
from flask import g
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from werkzeug.exceptions import abort

from shkeeper.auth import login_required
from shkeeper.modules.rates import RateSource
from shkeeper.modules.cryptos import Crypto
from shkeeper.models import (
    PayoutDestination,
    Wallet,
    PayoutPolicy,
    ExchangeRate,
    InvoiceStatus,
    Transaction,
)

bp = Blueprint("wallet", __name__)

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

    if request.method == "POST":
        pass

    return render_template("wallet/payout.j2", crypto=crypto, pdest=pdest)

@bp.route("/wallet/<crypto_name>")
@login_required
def manage(crypto_name):
    crypto = Crypto.instances[crypto_name]
    pdest = PayoutDestination.query.filter_by(crypto=crypto_name).all()
    wallet = Wallet.query.filter_by(crypto=crypto_name).first()

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
        crypto=crypto, pdest=pdest, ppolicy=[i.value for i in PayoutPolicy], recalc=recalc)


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
        txs=Transaction.query.all()
    )

