import enum
from datetime import datetime, timedelta
from decimal import Decimal

import bcrypt
from flask import current_app as app

from shkeeper import db
from shkeeper.modules.rates import RateSource
from shkeeper.modules.classes.crypto import Crypto
from .utils import format_decimal
from .exceptions import NotRelatedToAnyInvoice


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    passhash = db.Column(db.String(120))
    api_key = db.Column(db.String)

    @staticmethod
    def get_password_hash(password):
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))

    def verify_password(self, password):
        return bcrypt.checkpw(password.encode(), self.passhash)

    @classmethod
    def get_api_key(cls):
        return cls.query.first().api_key

class PayoutDestination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crypto = db.Column(db.String)
    addr = db.Column(db.String, nullable=False)
    comment = db.Column(db.String, default='')

    __table_args__ =  (
        db.UniqueConstraint('crypto', 'addr'),
    )


class PayoutPolicy(enum.Enum):
    MANUAL = 'manual'
    SCHEDULED = 'scheduled'
    LIMIT = 'limit'

class Fiat:

    @classmethod
    def list(cls):
        return ['USD', 'EUR']


class Wallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crypto = db.Column(db.String, unique=True, nullable=False)
    serverkey = db.Column(db.String)
    pdest = db.Column(db.String)
    pfee = db.Column(db.String)
    payout = db.Column(db.Boolean, default=False)
    ppolicy = db.Column(db.Enum(PayoutPolicy), default=PayoutPolicy.MANUAL)
    pcond = db.Column(db.String)
    last_payout_attempt = db.Column(db.DateTime, default=datetime.min)
    enabled = db.Column(db.Boolean, default=True)
    apikey = db.Column(db.String)
    llimit = db.Column(db.Numeric, default=95)
    ulimit = db.Column(db.Numeric, default=105)
    recalc = db.Column(db.Integer, default=0)
    confirmations = db.Column(db.Integer, default=1)
    bkey = db.Column(db.String)

    @classmethod
    def register_currency(cls, crypto):
        wallet = cls.query.filter_by(crypto=crypto.crypto).first()
        if not wallet:
            wallet = cls(crypto=crypto.crypto)
            db.session.add(wallet)
        if not wallet.apikey:
            if wallet_with_apikey := cls.query.filter(cls.apikey != None).first():
                wallet.apikey = wallet_with_apikey.apikey
            else:
                wallet.apikey = app.config['SUGGESTED_WALLET_APIKEY']
        db.session.commit()
        return wallet

    def do_payout(self):
        if not self.payout:
            return False

        self.last_payout_attempt = datetime.now()
        db.session.commit()

        crypto = Crypto.instances[self.crypto]
        balance = crypto.balance()
        res = crypto.mkpayout(self.pdest, balance, self.pfee, subtract_fee_from_amount=True)

        if 'result' in res and res['result']:
            idtxs = res['result'] if isinstance(res['result'], list) else [res['result']]
            Payout.add({'dest': self.pdest, 'amount': balance, 'txids': idtxs}, crypto.crypto)

        return res


class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String, default='dynamic')  # manual or dynamic (binance, etc)
    crypto = db.Column(db.String)
    fiat = db.Column(db.String)
    rate = db.Column(db.Numeric, default=0)  # crypto / fiat, only used is source is manual
    fee = db.Column(db.Numeric, default=2)
    __table_args__ = (db.UniqueConstraint('crypto', 'fiat'), )

    def get_rate(self):
        if self.source == 'manual':
            return self.rate

        rs = RateSource.instances.get(self.source, RateSource.instances.get('binance'))
        return rs.get_rate(self.fiat, self.crypto)

    def convert(self, amount):
        rate = self.get_rate()
        converted = (amount / rate) * (1 + (self.fee / 100))
        crypto = Crypto.instances[self.crypto]
        converted = round(converted, crypto.precision)
        return (converted, rate)

    @classmethod
    def get(cls, fiat, crypto):
        src = cls.query.filter_by(fiat=fiat,crypto=crypto).first()
        if not src:
            raise Exception(f"Exchange rate src config for {fiat}-{crypto} is not found")
        return src

    @classmethod
    def register_currency(cls, crypto):
        for fiat in Fiat.list():
            if not cls.query.filter_by(fiat=fiat,crypto=crypto.crypto).first():
                db.session.add(cls(fiat=fiat,crypto=crypto.crypto))
                db.session.commit()


class InvoiceStatus(enum.Enum):
    UNPAID = enum.auto()
    PARTIAL = enum.auto()
    PAID = enum.auto()
    OVERPAID = enum.auto()
    CANCELLED = enum.auto()
    REFUNDED = enum.auto()
    OUTGOING = enum.auto()


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transactions = db.relationship('Transaction', backref='invoice', lazy=True)
    addresses = db.relationship('InvoiceAddress', backref='invoice', lazy=True)
    crypto = db.Column(db.String)
    addr = db.Column(db.String)
    external_id = db.Column(db.String)
    fiat = db.Column(db.String)
    callback_url = db.Column(db.String)
    balance_fiat = db.Column(db.Numeric, default=0)
    balance_crypto = db.Column(db.Numeric, default=0)
    amount_fiat = db.Column(db.Numeric)
    amount_crypto = db.Column(db.Numeric)
    exchange_rate = db.Column(db.Numeric)
    status = db.Column(db.Enum(InvoiceStatus), default=InvoiceStatus.UNPAID)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                                        onupdate=db.func.current_timestamp())

    @property
    def wallet(self) -> Wallet:
        return Wallet.query.filter_by(crypto=self.crypto).first()

    @property
    def rate(self):
        return ExchangeRate.get(self.fiat, self.crypto)

    def update_with_tx(self, tx):

        # recalculate amount_crypto according to current exchange rate if enabled
        if tx.invoice.wallet.recalc > 0:
            if (tx.invoice.created_at + timedelta(hours=tx.invoice.wallet.recalc)) < datetime.now():
                tx.invoice.amount_crypto, tx.invoice.exchange_rate = tx.invoice.rate.convert(tx.invoice.amount_fiat)
                # recalculate tx fiat amount according to a new exchange rate
                tx.amount_fiat = tx.amount_crypto * tx.invoice.exchange_rate

        # add tx to invoice balance
        tx.invoice.balance_fiat += tx.amount_fiat
        if tx.crypto == tx.invoice.crypto:  # do not add different tokens e.g. TRX and TRC20 USDT
            tx.invoice.balance_crypto += tx.amount_crypto

        # change invoice status according to its new balance
        if tx.invoice.balance_fiat < (tx.invoice.amount_fiat * (tx.invoice.wallet.llimit / 100)):
            tx.invoice.status = InvoiceStatus.PARTIAL
        elif tx.invoice.balance_fiat < (tx.invoice.amount_fiat * (tx.invoice.wallet.ulimit / 100)):
            tx.invoice.status = InvoiceStatus.PAID
        else:
            tx.invoice.status = InvoiceStatus.OVERPAID

        db.session.commit()
        return self

    @classmethod
    def add(cls, crypto, request):
        # {"external_id": "1234",  "fiat": "USD", "amount": 100.90, "callback_url": "https://blabla/callback.php"}
        invoice = cls.query.filter_by(external_id=request['external_id'],
                                      callback_url=request['callback_url']).first()
        if invoice:
            # updating existing invoice
            if invoice.crypto != crypto.crypto:
                invoice.crypto = crypto.crypto

                # if address for new crypto already exist, use it instead of generating a new one
                invoice_address = InvoiceAddress.query.filter_by(invoice_id=invoice.id, crypto=crypto.crypto).first()
                if invoice_address:
                    invoice.addr = invoice_address.addr
                else:
                    invoice.addr = crypto.mkaddr()
                    invoice_address = InvoiceAddress()
                    invoice_address.invoice_id = invoice.id
                    invoice_address.crypto = invoice.crypto
                    invoice_address.addr = invoice.addr
                    db.session.add(invoice_address)

            invoice.fiat = request['fiat']
            invoice.amount_fiat = Decimal(request['amount'])
            rate = ExchangeRate.get(invoice.fiat, invoice.crypto)
            invoice.amount_crypto, invoice.exchange_rate = rate.convert(invoice.amount_fiat)
        else:
            # creating new invoice
            invoice = cls()
            invoice.crypto = crypto.crypto
            invoice.addr = crypto.mkaddr()
            invoice.external_id = request['external_id']
            invoice.callback_url = request['callback_url']
            invoice.fiat = request['fiat']
            invoice.amount_fiat = Decimal(request['amount'])
            rate = ExchangeRate.get(invoice.fiat, invoice.crypto)
            invoice.amount_crypto, invoice.exchange_rate = rate.convert(invoice.amount_fiat)
            db.session.add(invoice)
            db.session.commit()

            invoice_address = InvoiceAddress()
            invoice_address.invoice_id = invoice.id
            invoice_address.crypto = invoice.crypto
            invoice_address.addr = invoice.addr
            db.session.add(invoice_address)

        db.session.commit()
        return invoice

    def for_response(self):
        return {
            "id": self.id,
            "exchange_rate": format_decimal(self.exchange_rate, 2),
            "amount": format_decimal(self.amount_crypto),
            "wallet": self.addr,
            "recalculate_after": self.wallet.recalc,
            "display_name": Crypto.instances[self.crypto].display_name,
        }

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    txid = db.Column(db.String)
    crypto = db.Column(db.String)
    amount_crypto = db.Column(db.Numeric)
    amount_fiat = db.Column(db.Numeric)
    need_more_confirmations = db.Column(db.Boolean, default=True)
    callback_confirmed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                                        onupdate=db.func.current_timestamp())
    __table_args__ = (db.UniqueConstraint('crypto', 'txid', 'invoice_id'), )

    def __repr__(self):
        return f"txid={self.txid}"

    @property
    def addr(self):
        if invoice_address := InvoiceAddress.query.filter_by(crypto=self.crypto, invoice_id=self.invoice_id).first():
            return invoice_address.addr
        else:
            return self.invoice.addr

    @classmethod
    def add_outgoing(cls, crypto, txid):
        for addr, amount, _, _ in crypto.getaddrbytx(txid):
            payout_invoice = Invoice(
                addr=addr,
                fiat="USD",
                status=InvoiceStatus.OUTGOING
            )
            db.session.add(payout_invoice)
            db.session.commit()

            tx = cls()
            tx.invoice_id = payout_invoice.id
            tx.txid = txid
            tx.crypto = crypto.crypto
            tx.amount_crypto = amount
            rate = ExchangeRate.get(payout_invoice.fiat, tx.crypto).get_rate()
            tx.amount_fiat = tx.amount_crypto * rate
            tx.need_more_confirmations = False
            tx.callback_confirmed = True

            db.session.add(tx)
            db.session.commit()

    @classmethod
    def add(cls, crypto, tx):
        invoice_address = InvoiceAddress.query.filter_by(crypto=crypto.crypto, addr=tx['addr']).first()

        if not invoice_address:
            # Check address in Invoice table in case the instance was upgraded from older version that does not have InvoiceAddress table
            invoice = Invoice.query.filter_by(addr=tx['addr']).first()
        else:
            invoice = Invoice.query.filter_by(id=invoice_address.invoice_id).first()

        if not invoice:
            raise NotRelatedToAnyInvoice(f'{tx["addr"]} is not related to any invoice')

        t = cls()
        t.invoice_id = invoice.id
        t.txid = tx['txid']
        t.crypto = crypto.crypto
        t.amount_crypto = tx['amount']
        if invoice.crypto != crypto.crypto:
            rate = ExchangeRate.get(invoice.fiat, crypto.crypto).get_rate()
            t.amount_fiat = t.amount_crypto * rate
        else:
            t.amount_fiat = t.amount_crypto * invoice.exchange_rate

        if tx['confirmations'] >= crypto.wallet.confirmations:
            t.need_more_confirmations = False

        db.session.add(t)
        db.session.commit()
        return t

    def is_more_confirmations_needed(self):
        crypto = Crypto.instances[self.crypto]
        confirmations = crypto.get_confirmations_by_txid(self.txid)
        if confirmations >= self.invoice.wallet.confirmations:
            self.need_more_confirmations = False
            db.session.commit()
        return self.need_more_confirmations


class PayoutStatus(enum.Enum):
    IN_PROGRESS = enum.auto()
    SUCCESS = enum.auto()
    FAIL = enum.auto()

class Payout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                                        onupdate=db.func.current_timestamp())
    amount = db.Column(db.Numeric)
    crypto = db.Column(db.String)
    dest_addr = db.Column(db.String)
    status = db.Column(db.Enum(PayoutStatus), default=PayoutStatus.IN_PROGRESS)
    transactions = db.relationship('PayoutTx', backref='payout', lazy=True)

    @classmethod
    def add(cls, payout, crypto):
        p = cls(
            dest_addr = payout['dest'],
            amount = payout['amount'],
            crypto = crypto,
        )
        db.session.add(p)
        db.session.commit()

        for txid in payout['txids']:
            ptx = PayoutTx(
                payout_id = p.id,
                txid = txid
            )
            db.session.add(ptx)

        db.session.commit()


class PayoutTxStatus(enum.Enum):
    IN_PROGRESS = enum.auto()
    SUCCESS = enum.auto()
    FAIL = enum.auto()

class PayoutTx(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payout_id = db.Column(db.Integer, db.ForeignKey('payout.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(),
                                        onupdate=db.func.current_timestamp())
    txid = db.Column(db.String)
    status = db.Column(db.Enum(PayoutTxStatus), default=PayoutTxStatus.IN_PROGRESS)


class Setting(db.Model):
    name = db.Column(db.String, primary_key=True)
    value = db.Column(db.String)


class InvoiceAddress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    crypto = db.Column(db.String)
    addr = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    __table_args__ = (db.UniqueConstraint('invoice_id', 'crypto', 'addr'), )
