from decimal import Decimal
from datetime import timedelta, datetime

from flask_apscheduler import APScheduler
from shkeeper import scheduler, callback
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.nano import Nano, nano_to_raw, raw_to_nano
from shkeeper.models import *

@scheduler.task("interval", id="callback", seconds=60)
def task_callback():
    with scheduler.app.app_context():
        callback.update_confirmations()
        callback.send_callbacks()

@scheduler.task("interval", id="pending_payouts", seconds=60)
def task_poll_all_pending_payouts():
    with scheduler.app.app_context():
        callback.poll_all_pending_payouts()

@scheduler.task("interval", id="unconfirmed_payouts", seconds=60)
def task_poll_unconfirmed_payouts():
    with scheduler.app.app_context():
        callback.poll_unconfirmed_payouts()

@scheduler.task("interval", id="payout_callback_notifier", seconds=60)
def task_send_payout_callback_notifier():
    with scheduler.app.app_context():
        if not scheduler.app.config.get("ENABLE_PAYOUT_CALLBACK"):
            return
        callback.send_payout_callback_notifier()

@scheduler.task("interval", id="payout", seconds=60)
def task_payout():
    scheduler.app.logger.info(f"[Autopayout] Task started")
    with scheduler.app.app_context():
        for crypto in Crypto.instances.values():
            if crypto.wallet.ppolicy == PayoutPolicy.LIMIT:
                scheduler.app.logger.info(
                    f"[Autopayout] {crypto.crypto} payout policy is {crypto.wallet.ppolicy}"
                )
                limit = Decimal(crypto.wallet.pcond)
                if crypto.balance() >= limit:
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} payout limit reached. "
                        f"Need: {limit}, has: {crypto.balance()}"
                    )
                    res = crypto.wallet.do_payout()
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} payout response: {res}"
                    )
                else:
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} payout limit is not reached. "
                        f"Need: {limit}, has: {crypto.balance()}"
                    )

            elif crypto.wallet.ppolicy == PayoutPolicy.SCHEDULED:
                scheduler.app.logger.info(
                    f"[Autopayout] {crypto.crypto} payout policy is {crypto.wallet.ppolicy}"
                )
                if crypto.balance() == 0:
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} has no coins"
                    )
                    continue
                interval = int(crypto.wallet.pcond)
                next_payout_attempt = crypto.wallet.last_payout_attempt + timedelta(
                    minutes=interval
                )
                now = datetime.now()
                if next_payout_attempt < now:
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} payout attempt is now."
                    )
                    res = crypto.wallet.do_payout()
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} payout response: {res}"
                    )
                else:
                    scheduler.app.logger.info(
                        f"[Autopayout] {crypto.crypto} next payout attempt "
                        f"scheduled after {next_payout_attempt}."
                    )


@scheduler.task("interval", id="create_wallet", seconds=10)
def task_create_wallet():
    with scheduler.app.app_context():
        if all([c.wallet_created for c in Crypto.instances.values()]):
            scheduler.app.logger.info(
                f"[Create Wallet] All cryptos has its wallets loaded. Deleting the task."
            )
            scheduler.delete_job("create_wallet")
            return

        for crypto in Crypto.instances.values():
            if crypto.wallet_created:
                continue
            try:
                scheduler.app.logger.info(
                    f"[task_create_wallet()] Calling create_wallet() for {crypto.crypto}"
                )
                res = crypto.create_wallet()
                if not res["error"]:
                    scheduler.app.logger.info(
                        f"[Create Wallet] {crypto.crypto} "
                        "shkeeper wallet has been created."
                    )
                    crypto.wallet_created = True
                    continue

                if res["error"]["code"] == -4:
                    scheduler.app.logger.info(
                        f"[Create Wallet] {crypto.crypto} "
                        f"shkeeper wallet already exists."
                    )
                    crypto.wallet_created = True
                    continue

                else:
                    scheduler.app.logger.info(
                        f"[Create Wallet] {crypto.crypto} shkeeper wallet "
                        f'creation error: {res["error"]["message"]}'
                    )
            except Exception as e:
                scheduler.app.logger.exception(
                    f"[Create Wallet] {crypto.crypto} shkeeper wallet "
                    f"creation error: {e}"
                )


@scheduler.task("interval", id="nano_receive_pending", seconds=30)
def task_nano_receive_pending():
    """Poll for pending Nano transactions and receive them."""
    with scheduler.app.app_context():
        for crypto in Crypto.instances.values():
            if not isinstance(crypto, Nano):
                continue
            if not crypto.wallet or not crypto.wallet.enabled:
                continue

            try:
                # Get all addresses we're monitoring
                addresses = crypto.get_all_addresses()
                scheduler.app.logger.info(f"[Nano] get_all_addresses() returned: {addresses}")
                if not addresses:
                    scheduler.app.logger.warning(f"[Nano] No addresses found for {crypto.crypto}")
                    continue

                scheduler.app.logger.info(f"[Nano] Checking {len(addresses)} addresses for pending blocks")

                for address in addresses:
                    # Check for pending blocks
                    pending = crypto._rpc_request(
                        "receivable",
                        account=address,
                        count="100"
                    )

                    scheduler.app.logger.info(f"[Nano] receivable response for {address}: {pending}")

                    blocks = pending.get("blocks", [])
                    if isinstance(blocks, dict):
                        blocks = list(blocks.keys())
                    if not blocks:
                        continue

                    scheduler.app.logger.info(f"[Nano] Found {len(blocks)} pending blocks for {address}")

                    # Receive pending blocks
                    received = crypto.receive_pending(address)

                    # For each received block, create a transaction record
                    for block_hash in received:
                        try:
                            # Get block info
                            block_info = crypto._rpc_request("block_info", json_block="true", hash=block_hash)
                            amount_raw = block_info.get("amount", "0")
                            amount = raw_to_nano(int(amount_raw))

                            # Add transaction to database
                            from shkeeper.models import Transaction
                            tx = Transaction.add(
                                crypto,
                                {
                                    "txid": block_hash,
                                    "addr": address,
                                    "amount": amount,
                                    "confirmations": 1,  # Nano is instant
                                }
                            )
                            scheduler.app.logger.info(f"[Nano] Received {amount} XNO to {address}, tx: {block_hash}")
                        except Exception as e:
                            scheduler.app.logger.error(f"[Nano] Failed to record transaction {block_hash}: {e}")

            except Exception as e:
                scheduler.app.logger.exception(f"[Nano] Error checking pending for {crypto.crypto}: {e}")
