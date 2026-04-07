import click
from os import environ

from shkeeper import requests
from shkeeper import db
from flask import Blueprint, json
from flask import current_app as app

from shkeeper.modules.classes.crypto import Crypto
from shkeeper.services.withdraw_service import WithdrawService
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


def withdraw_to_external_wallet(crypto_name, source, destination, invoice_external_id):
    payout_list = [{'dest': destination, 'source': source}]
    app.logger.info(f"Start withdraw invoice {invoice_external_id} to external wallet {crypto_name} {payout_list}")
    try:
        crypto = Crypto.instances[crypto_name]
    except KeyError:
        raise ValueError(f"Unknown crypto: {crypto_name}")
    #res = crypto.withdraw_to_external_wallet(payout_list)
    res = WithdrawService.single_withdraw(crypto_name, payout_list, invoice_external_id)
    return res


def get_tx_address(crypto_name, txid):
    try:
        crypto = Crypto.instances[crypto_name]
    except KeyError:
        raise ValueError(f"Unknown crypto: {crypto_name}")
    tx_data_from_crypto = crypto.getaddrbytx(txid)
    tx_address = tx_data_from_crypto[0][0]
    return tx_address

def get_invoice_address_status(invoice_external_id, crypto, source_address):
    invoice_payouts = Payout.query.filter(Payout.external_id.like(str(f'withdraw***{invoice_external_id}***{crypto}***{source_address}%'))).all()
    have_status = False
    for payout in invoice_payouts:
        app.logger.info(f"Check payout {payout.id} with status {payout.status} for invoice {invoice_external_id}")
        if payout.status == PayoutStatus.SUCCESS:
            have_status = "SUCCESS"
    app.logger.info(f"Have status {have_status} for invoice {invoice_external_id} and address {source_address}")
    return have_status  

def check_all_paid_invoices():
    app.logger.info(f"Check all invoices")
    paid_and_overpaid_invoices = (
    Invoice.query
    .filter(Invoice.status.in_([InvoiceStatus.PAID, 
                                InvoiceStatus.OVERPAID,])).all())

    for invoice in paid_and_overpaid_invoices:
        skip_invoice = False
        invoice_transactions = Transaction.query.filter_by(invoice_id = invoice.id)
        invoice_tx_aml_scores = []
        invoice_tx_cryptos = []

        for tx in invoice_transactions:
            invoice_tx_cryptos.append(tx.crypto)
        
        for tx_crypto in invoice_tx_cryptos:
            try:
                crypto_inst = Crypto.instances[tx_crypto]
            except KeyError:
                app.logger.info(f"Transaction crypto {tx_crypto} in {invoice.external_id} is unavailable now, skip invoice")
                skip_invoice = True
                break

        
        if skip_invoice: 
            app.logger.info(f"Skip invoice {invoice.external_id}")
            continue


        for tx in invoice_transactions:
            tx_address = get_tx_address(tx.crypto, tx.txid)
            
            aml_result = get_tx_aml_score(tx.crypto, 
                                         tx.txid, 
                                         tx.amount_crypto, 
                                         tx_address)
            if not aml_result:
                app.logger.info(f"Cannot get info for {tx.txid} tx, skip invoice")
                skip_invoice = True
            else:
                aml_score = aml_result['aml_score']
                invoice_tx_aml_scores.append(aml_score)

                if (float(aml_score) > -1) or  (float(aml_score) == -2):
                    if tx.aml_score == aml_score:
                        app.logger.info("No need to update the tx")
                    else:
                        app.logger.info("Update TX with AML scores")
                        tx.aml_score = aml_score
                        tx.callback_confirmed = False
                        db.session.commit()
        
        
        if skip_invoice: 
            app.logger.info(f"Skip invoice {invoice.external_id}")
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

        without_failed_aml_score = True
        for aml_score in invoice_tx_aml_scores:
            if aml_score == -2:
                # one invoice transaction failed to get AML score
                # invoice should be AML_CHECK_FAILED
                app.logger.info(f"One of {invoice.external_id,} transactions failed to get AML score")
                invoice.status = InvoiceStatus.AML_CHECK_FAILED
                db.session.commit()
                without_failed_aml_score = False
        if not without_failed_aml_score:
            continue 
        
        all_aml_scores_above_limit = True
        for aml_score in invoice_tx_aml_scores:
            if -1 < aml_score > app.config.get("AML_MAX_ACCEPT_SCORE"):
                # one invoice transaction is above the AML_MAX_ACCEPT_SCORE
                # invoice should be DECLINED
                app.logger.info(f"One of {invoice.external_id} transactions above the AML_MAX_ACCEPT_SCORE, should refunded manually")
                invoice.status = InvoiceStatus.AML_CHECK_DECLINED
                db.session.commit()
                all_aml_scores_above_limit = False
        if not all_aml_scores_above_limit:
            continue  
        
        # invoice has all scores and all below the AML_MAX_ACCEPT_SCORE
        # invoice should be AML_CHECK_PAID or AML_CHECK_OVERPAID
            
        if invoice.status == InvoiceStatus.PAID:
            invoice.status = InvoiceStatus.AML_CHECK_PAID
            db.session.commit()
        elif invoice.status == InvoiceStatus.OVERPAID:
            invoice.status = InvoiceStatus.AML_CHECK_OVERPAID
            db.session.commit()
        else:
            pass
        
        #if we here - all aml_scores are lower than AML_MAX_ACCEPT_SCORE
        all_crypto_pairs = []
        for tx in invoice_transactions:
            tx_address = get_tx_address(tx.crypto, tx.txid)
            all_crypto_pairs.append((tx.crypto, tx_address))

        uniq_pairs = list(set(all_crypto_pairs))

        for tx_crypto, tx_address in uniq_pairs:
            withdraw_to_external_wallet(tx_crypto, 
                                     tx_address, 
                                     app.config.get("AML_EXTERNAL_ADDRESSES")[tx_crypto],
                                     invoice.external_id)


def recheck_all_aml_invoices():
    # with app.app_context():
    app.logger.info(f"Reheck all AML invoices")
    paid_and_overpaid_invoices = (
    Invoice.query
    .filter(Invoice.status.in_([InvoiceStatus.AML_CHECK_PAID,
                                InvoiceStatus.AML_CHECK_OVERPAID,])).all())

    for invoice in paid_and_overpaid_invoices:
        skip_invoice = False
        invoice_transactions = Transaction.query.filter_by(invoice_id = invoice.id)
        invoice_tx_aml_scores = []
        invoice_tx_cryptos = []
        for tx in invoice_transactions:
            invoice_tx_cryptos.append(tx.crypto)

        for tx_crypto in invoice_tx_cryptos:
            try:
                crypto_inst = Crypto.instances[tx_crypto]
            except KeyError:
                app.logger.info(f"Transaction crypto {tx_crypto} in {invoice.external_id} is unavailable now, skip invoice")
                skip_invoice = True
                break
        
        if skip_invoice: 
            app.logger.info(f"Skip invoice {invoice.external_id}")
            continue


        for tx in invoice_transactions:
            try:
                tx_address = get_tx_address(tx.crypto, tx.txid)
                aml_result = get_tx_aml_score(tx.crypto, 
                                         tx.txid, 
                                         tx.amount_crypto, 
                                         tx_address)
            except Exception as e:
                app.logger.info(f"Error while getting AML score for {tx.txid} tx, skip invoice - {e}")
                aml_result = False

            if not aml_result:
                app.logger.info(f"Cannot get info for {tx.txid} tx, skip invoice")
                skip_invoice = True
            else:
                aml_score = aml_result['aml_score']
                invoice_tx_aml_scores.append(aml_score)

        if skip_invoice: 
            app.logger.info(f"Skip invoice {invoice.external_id}")
            continue
            
        all_aml_scores_above_limit = True

        for aml_score in invoice_tx_aml_scores:
            if -1 < aml_score > app.config.get("AML_MAX_ACCEPT_SCORE"):
                # one invoice transaction is above the AML_MAX_ACCEPT_SCORE
                # invoice should be DECLINED
                app.logger.info(f"One of {invoice.external_id,} transactions above the AML_MAX_ACCEPT_SCORE, should refunded manually")
                invoice.status = InvoiceStatus.AML_CHECK_DECLINED
                db.session.commit()
                all_aml_scores_above_limit = False

        if not all_aml_scores_above_limit:
            continue  

        all_crypto_pairs = []
        for tx in invoice_transactions:
            tx_address = get_tx_address(tx.crypto, tx.txid)
            all_crypto_pairs.append((tx.crypto, tx_address))

        uniq_pairs = list(set(all_crypto_pairs))

        app.logger.info(f"Uniq crypto, address pairs for  {invoice.external_id} invoice - {uniq_pairs}")   

        invoice_withdrew = True
        for tx_crypto, tx_address in uniq_pairs:    
            tx_payout_status = get_invoice_address_status(invoice.external_id, tx_crypto, tx_address)
            if not tx_payout_status or tx_payout_status == "FAIL" or tx_payout_status == "IN_PROGRESS":
                app.logger.info(f"One of {invoice.external_id,} payouts from {tx_address} failed or in progress, try to withdraw again")
                invoice_withdrew = False
                withdraw_to_external_wallet(tx.crypto, 
                                        tx_address, 
                                        app.config.get("AML_EXTERNAL_ADDRESSES")[tx.crypto],
                                        invoice.external_id)

        if invoice_withdrew:
            invoice.status = InvoiceStatus.AML_CHECK_TRANSFERRED
            db.session.commit()

