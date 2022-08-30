from decimal import Decimal
from datetime import timedelta, datetime

from flask_apscheduler import APScheduler

from shkeeper import scheduler, callback
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.models import *


@scheduler.task("interval", id="callback", seconds=60)
def task_callback():
    with scheduler.app.app_context():
        callback.update_confirmations()
        callback.send_callbacks()


@scheduler.task("interval", id="payout", seconds=60)
def task_payout():
    scheduler.app.logger.info(f'[Autopayout] Task started')
    with scheduler.app.app_context():
        for crypto in Crypto.instances.values():

            if crypto.wallet.ppolicy == PayoutPolicy.LIMIT:
                scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout policy is {crypto.wallet.ppolicy}')
                limit = Decimal(crypto.wallet.pcond)
                if crypto.balance() >= limit:
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout limit reached. '
                                              f'Need: {limit}, has: {crypto.balance()}')
                    res = crypto.wallet.do_payout()
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout response: {res}')
                else:
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout limit is not reached. '
                                              f'Need: {limit}, has: {crypto.balance()}')

            elif crypto.wallet.ppolicy == PayoutPolicy.SCHEDULED:
                scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout policy is {crypto.wallet.ppolicy}')
                if crypto.balance() == 0:
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} has no coins')
                    continue
                interval = int(crypto.wallet.pcond)
                next_payout_attempt = crypto.wallet.last_payout_attempt + timedelta(minutes=interval)
                now = datetime.now()
                if next_payout_attempt < now:
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout attempt is now.')
                    res = crypto.wallet.do_payout()
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} payout response: {res}')
                else:
                    scheduler.app.logger.info(f'[Autopayout] {crypto.crypto} next payout attempt '
                                              f'scheduled after {next_payout_attempt}.')


@scheduler.task("interval", id="create_wallet", seconds=60)
def task_create_wallet():
    with scheduler.app.app_context():

        if all([c.wallet_created for c in Crypto.instances.values()]):
            scheduler.app.logger.info(f'[Create Wallet] All cryptos has its wallets loaded. Deleting the task.')
            scheduler.delete_job('create_wallet')
            return

        for crypto in Crypto.instances.values():
            if crypto.wallet_created:
                continue
            try:
                res = crypto.create_wallet()
                if not res['error']:
                    scheduler.app.logger.info(f'[Create Wallet] {crypto.crypto} '
                                                'shkeeper wallet has been created.')
                    crypto.wallet_created = True
                    continue

                if res['error']['code'] == -4:
                    scheduler.app.logger.info(f'[Create Wallet] {crypto.crypto} '
                                              f'shkeeper wallet already exists.')
                    crypto.wallet_created = True
                    continue

                else:
                    scheduler.app.logger.info(f'[Create Wallet] {crypto.crypto} shkeeper wallet '
                                              f'creation error: {res["error"]["message"]}')
            except Exception as e:
                scheduler.app.logger.info(f'[Create Wallet] {crypto.crypto} shkeeper wallet '
                                          f'creation error: {e}')
