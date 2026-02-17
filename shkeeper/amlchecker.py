import click
from os import environ

from shkeeper import requests
from shkeeper import db
from flask import Blueprint, json
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import *
from datetime import datetime, timedelta

bp = Blueprint("callback", __name__)

DEFAULT_CURRENCY = 'USD'


def get_auth_creds():
    username = environ.get(f"AML_USERNAME", "shkeeper")
    password = environ.get(f"AML_PASSWORD", "shkeeper")
    return (username, password)


def check_tx_aml(crypto, txid, amount, account):
    tx_info = {'hash': txid, 'account': account, 'amount': float(amount)}
    app.logger.info(f'AML check {tx_info}')
    response = requests.post(
        f"http://aml-shkeeper:6000/{crypto}/check_tx",
        auth=get_auth_creds(),
        json=tx_info,
    ).json(parse_float=Decimal)
    return response


def get_tx_aml_score(crypto, txid, amount, account):
    response = requests.get(
        f"http://aml-shkeeper:6000/{crypto}/get_score/{txid}",
        auth=get_auth_creds(),
    ).json(parse_float=Decimal)

    if response['status'] == 'success':
        return response
    
    elif ((response['status'] == 'error') and
        (response['msg'] == 'txid not found')):
        response = check_tx_aml(crypto, txid, amount, account)

        if response['status'] == 'success':
            return response
    
    app.logger.info(f"Unexpected error result {response}")
    return False


def withdraw_to_external_wallet(crypto_name, source, destination):
    payout_list = [{'dest': destination, 'source': source}]
    app.logger.info(f"Start withdraw to external wallet {crypto_name} {payout_list}")
    try:
        crypto = Crypto.instances[crypto_name]
    except KeyError:
        raise ValueError(f"Unknown crypto: {crypto_name}")
    res = crypto.withdraw_to_external_wallet(payout_list)
    return res


def check_all_paid_invoices():
    # with app.app_context():
    app.logger.info(f"Check all invoices")
    paid_and_overpaid_invoices = (
    Invoice.query
    .filter(Invoice.status.in_([InvoiceStatus.PAID, 
                                InvoiceStatus.OVERPAID,
                                InvoiceStatus.AML_CHECK_PAID,
                                InvoiceStatus.AML_CHECK_OVERPAID,]))
    .all()
    )



    for invoice in paid_and_overpaid_invoices:
        skip_invoice = False
        invoice_transactions = Transaction.query.filter_by(invoice_id = invoice.id)
        invoice_tx_aml_scores = []
        invoice_tx_cryptos = []
        for tx in invoice_transactions:
            tx_address = InvoiceAddress.query.filter(InvoiceAddress.invoice_id == invoice.id, 
                                                     InvoiceAddress.crypto == tx.crypto).first()
            aml_result = get_tx_aml_score(tx.crypto, 
                                         tx.txid, 
                                         tx.amount_crypto, 
                                         tx_address.addr)
            if not aml_result:
                app.logger.info(f"Cannot get info for {tx.txid} tx, skip invoice")
                skip_invoice = True
            else:
                aml_score = aml_result['aml_score']
            invoice_tx_aml_scores.append(aml_score)
            invoice_tx_cryptos.append(tx.crypto)
            if float(aml_score) > -1:
                if tx.aml_score == aml_score:
                    app.logger.info("No need to update the tx")
                else:
                    app.logger.info("Update TX with AML scores")
                    tx.aml_score = aml_score
                    tx.callback_confirmed = False
                    db.session.commit()
        
        if skip_invoice: 
            app.logger.info(f"Skip invoce {invoice.external_id}")
            continue

        app.logger.info(f"Invoice {invoice.external_id} have next txs scores: {invoice_tx_aml_scores}")
        has_all_aml_scores = True
        for aml_score in invoice_tx_aml_scores:
            if aml_score == -1:
                # not all txs received aml results, give up for this invoice
                app.logger.info(f"Invoice {invoice.external_id} have not all AML scores, skip it for now")
                has_all_aml_scores = False
        if not has_all_aml_scores:
            continue  
        
        all_aml_scores_above_limit = True
        for aml_score in invoice_tx_aml_scores:
            if -1 < aml_score < app.config.get("AML_MIN_ACCEPT_SCORE"):
                # one invoice transaction is below the AML_MIN_ACCEPT_SCORE
                # invoice should be DECLINED
                app.logger.info(f"One of {invoice.external_id,} transactions below the AML_MIN_ACCEPT_SCORE, should refunded manually")
                invoice.status = InvoiceStatus.AML_CHECK_DECLINED
                db.session.commit()
                all_aml_scores_above_limit = False
        if not all_aml_scores_above_limit:
            continue  
        
        # invoice has all scores and all above the AML_MIN_ACCEPT_SCORE
        # invoice should be AML_CHECK_PAID or AML_CHECK_OVERPAID
            
        if invoice.status == InvoiceStatus.PAID:
            invoice.status = InvoiceStatus.AML_CHECK_PAID
            db.session.commit()
        elif invoice.status == InvoiceStatus.OVERPAID:
            invoice.status = InvoiceStatus.AML_CHECK_OVERPAID
            db.session.commit()
        else:
            pass
            # app.logger.info(f'Incorrect invoice {invoice.external_id} status in this context, should be paid or overpaid')
            # continue  
        
        #if we here - all aml_scores are higher than AML_MIN_ACCEPT_SCORE
        for tx in invoice_transactions:
            # with app.app_context():
            tx_address = InvoiceAddress.query.filter(InvoiceAddress.invoice_id == invoice.id, 
                                                     InvoiceAddress.crypto == tx.crypto).first()
            withdraw_to_external_wallet(tx.crypto, 
                                     tx_address.addr, 
                                     app.config.get("AML_EXTERNAL_ADDRESSES")[tx.crypto])


