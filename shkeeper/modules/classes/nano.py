"""
Nano (XNO) base class for cryptocurrency operations.

Uses nanopy library for local key generation and block signing.
Works with any Nano RPC endpoint (public or private node).

Key features:
- Local seed/key management (stored encrypted in database)
- Works with public RPCs (no wallet_create needed)
- Feeless transactions
- Block signing done locally
"""

import datetime
import json
import os
import secrets
import threading
from decimal import Decimal
from typing import List, Tuple, Literal, Optional

import nanopy
from flask import current_app as app

from shkeeper import requests, db
from shkeeper.models import Setting
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.wallet_encryption import wallet_encryption


# 1 XNO = 10^30 raw
RAW_PER_NANO = Decimal("1000000000000000000000000000000")

# Nano address prefix
nanopy.account_prefix = "nano_"


def nano_to_raw(nano_amount: Decimal) -> int:
    """Convert Nano amount to raw (integer)."""
    return int(nano_amount * RAW_PER_NANO)


def raw_to_nano(raw_amount) -> Decimal:
    """Convert raw amount to Nano."""
    return Decimal(str(raw_amount)) / RAW_PER_NANO


class Nano(Crypto):
    """
    Base class for Nano (XNO) cryptocurrency.

    Uses nanopy for local key management and works with any Nano RPC.
    """

    # Nano is feeless
    can_set_tx_fee = False
    has_autopayout = True

    # Display precision (actual is 30 decimals in raw)
    precision = 6
    fee_description = "No fees"

    # Wallet created flag - set to True after seed is generated
    wallet_created = False

    # Default representative
    DEFAULT_REPRESENTATIVE = "nano_3pg8khw8gs94c1qeq9741n99ubrut8sj3n9kpntim1rm35h4wdzirofazmwt"

    def __init__(self):
        self.crypto = "XNO"

        # RPC configuration - works with any Nano RPC
        self.NANO_RPC_URL = os.environ.get(
            "NANO_RPC_URL",
            os.environ.get("NANO_RPC_HOST", "https://rpc.nano.to")
        )
        # If just a host is provided, construct URL
        if not self.NANO_RPC_URL.startswith("http"):
            port = os.environ.get("NANO_RPC_PORT", "7076")
            self.NANO_RPC_URL = f"http://{self.NANO_RPC_URL}:{port}"

        # Representative for delegating voting weight
        self.NANO_REPRESENTATIVE = os.environ.get(
            "NANO_REPRESENTATIVE",
            self.DEFAULT_REPRESENTATIVE
        )

        # Database setting names for this crypto
        self._seed_setting_name = f"{self.crypto.lower()}_wallet_seed"
        self._addresses_setting_name = f"{self.crypto.lower()}_addresses"
        self._address_index_setting_name = f"{self.crypto.lower()}_address_index"

    def getname(self):
        return "Nano"

    def gethost(self):
        return self.NANO_RPC_URL

    def _rpc_request(self, action: str, **params) -> dict:
        """
        Make a request to the Nano RPC.
        """
        payload = {"action": action, **params}

        try:
            response = requests.post(
                self.NANO_RPC_URL,
                json=payload,
                timeout=30,
            )
            result = response.json(parse_float=Decimal)

            if "error" in result:
                app.logger.error(f"Nano RPC error for {action}: {result['error']}")

            return result
        except requests.exceptions.RequestException as e:
            app.logger.exception(f"Nano RPC request failed for {action}")
            raise

    # ==================== Seed/Key Management ====================

    def _generate_seed(self) -> str:
        """Generate a new random 64-character hex seed."""
        return secrets.token_hex(32).upper()

    def _get_seed(self) -> Optional[str]:
        """Get the encrypted seed from database and decrypt it."""
        setting = Setting.query.get(self._seed_setting_name)
        if setting and setting.value:
            try:
                return wallet_encryption.decrypt_text(setting.value)
            except Exception as e:
                app.logger.error(f"Failed to decrypt Nano seed: {e}")
                return None
        return None

    def _save_seed(self, seed: str):
        """Encrypt and save seed to database."""
        encrypted_seed = wallet_encryption.encrypt_text(seed)
        setting = Setting.query.get(self._seed_setting_name)
        if setting:
            setting.value = encrypted_seed
        else:
            setting = Setting(name=self._seed_setting_name, value=encrypted_seed)
            db.session.add(setting)
        db.session.commit()
        app.logger.info(f"Nano seed saved to database")

    def _get_address_index(self) -> int:
        """Get the current address derivation index."""
        setting = Setting.query.get(self._address_index_setting_name)
        if setting and setting.value:
            return int(setting.value)
        return 0

    def _increment_address_index(self) -> int:
        """Increment and return the new address index."""
        current = self._get_address_index()
        new_index = current + 1
        setting = Setting.query.get(self._address_index_setting_name)
        if setting:
            setting.value = str(new_index)
        else:
            setting = Setting(name=self._address_index_setting_name, value=str(new_index))
            db.session.add(setting)
        db.session.commit()
        return new_index

    def _derive_keypair(self, seed: str, index: int) -> Tuple[str, str, str]:
        """
        Derive private key, public key, and address from seed and index.

        Returns: (private_key, public_key, address)
        """
        # nanopy.deterministic_key(seed, i) returns a 64-char hex private key
        # Use Account class to derive public key and address
        private_key = nanopy.deterministic_key(seed, index)
        acc = nanopy.Account()
        acc.sk = private_key
        public_key = acc.pk
        address = acc.addr  # 'addr' not 'address'
        return private_key.upper(), public_key.upper(), address

    def _get_private_key_for_address(self, address: str) -> Optional[str]:
        """Get the private key for a given address."""
        seed = self._get_seed()
        if not seed:
            return None

        # Search through derived addresses to find the matching one
        addresses_json = self._get_addresses_json()
        if address in addresses_json:
            index = addresses_json[address]
            private_key, _, _ = self._derive_keypair(seed, index)
            return private_key

        return None

    def _get_public_key_for_address(self, address: str) -> Optional[str]:
        """Get the public key for a given address."""
        seed = self._get_seed()
        if not seed:
            return None

        # Search through derived addresses to find the matching one
        addresses_json = self._get_addresses_json()
        if address in addresses_json:
            index = addresses_json[address]
            _, public_key, _ = self._derive_keypair(seed, index)
            return public_key

        return None

    def _get_addresses_json(self) -> dict:
        """Get the address -> index mapping from database."""
        setting = Setting.query.get(self._addresses_setting_name)
        if setting and setting.value:
            try:
                return json.loads(setting.value)
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_address_mapping(self, address: str, index: int):
        """Save address -> index mapping to database."""
        addresses = self._get_addresses_json()
        addresses[address] = index

        setting = Setting.query.get(self._addresses_setting_name)
        if setting:
            setting.value = json.dumps(addresses)
        else:
            setting = Setting(name=self._addresses_setting_name, value=json.dumps(addresses))
            db.session.add(setting)
        db.session.commit()

    # ==================== Crypto Interface Implementation ====================

    def balance(self) -> Decimal:
        """Get the total balance of all managed addresses."""
        try:
            addresses = list(self._get_addresses_json().keys())
            if not addresses:
                return Decimal(0)

            total_balance = Decimal(0)

            for address in addresses:
                result = self._rpc_request(
                    "account_balance",
                    account=address,
                    include_only_confirmed="true"
                )
                if "error" not in result:
                    balance_raw = result.get("balance", "0")
                    total_balance += raw_to_nano(balance_raw)

            return total_balance

        except Exception as e:
            app.logger.exception("Failed to get Nano balance")
            return Decimal(0)

    def getstatus(self) -> str:
        """Get the sync status of the Nano RPC endpoint."""
        try:
            result = self._rpc_request("block_count")

            if "error" in result:
                return "Offline"

            count = int(result.get("count", 0))
            cemented = int(result.get("cemented", 0))

            # Try to get network block count from telemetry
            telemetry = self._rpc_request("telemetry")
            if "error" not in telemetry:
                network_count = int(telemetry.get("block_count", count))
                if count >= network_count - 100:
                    return "Synced"
                else:
                    behind = network_count - count
                    return f"Sync In Progress ({behind} blocks behind)"

            # Fallback: assume synced if we got a response
            return "Synced"

        except Exception as e:
            app.logger.exception("Failed to get Nano status")
            return "Offline"

    def mkaddr(self, **kwargs) -> str:
        """Create a new Nano address from the seed."""
        seed = self._get_seed()
        if not seed:
            raise Exception("Nano wallet not initialized. Call create_wallet() first.")

        # Get next index and derive address
        index = self._get_address_index()
        private_key, public_key, address = self._derive_keypair(seed, index)

        # Save mapping and increment index
        self._save_address_mapping(address, index)
        self._increment_address_index()

        app.logger.info(f"Created new Nano address: {address} (index {index})")
        return address

    def getaddrbytx(self, block_hash: str) -> List[Tuple[str, Decimal, int, Literal["send", "receive"]]]:
        """Get transaction details by block hash."""
        result = self._rpc_request("block_info", json_block="true", hash=block_hash)

        if "error" in result:
            raise Exception(f"Failed to get block info for {block_hash}: {result['error']}")

        # Determine confirmation status
        confirmed = result.get("confirmed", "false") == "true"
        confirmations = 1 if confirmed else 0

        # Get block contents
        contents = result.get("contents", {})
        if isinstance(contents, str):
            contents = json.loads(contents)

        subtype = result.get("subtype", "")
        account = contents.get("account", result.get("block_account", ""))

        # Get amount
        amount_raw = result.get("amount", "0")
        amount = raw_to_nano(amount_raw)

        if subtype == "send":
            category = "send"
            destination = contents.get("link_as_account", "")
            if not destination:
                # Convert link to account
                link = contents.get("link", "")
                if link and link != "0" * 64:
                    try:
                        destination = nanopy.account_get(link)
                    except:
                        destination = ""
            details = [(destination, amount, confirmations, category)]
        elif subtype in ("receive", "open"):
            category = "receive"
            details = [(account, amount, confirmations, category)]
        else:
            category = subtype or "unknown"
            details = [(account, Decimal(0), confirmations, category)]

        return details

    def get_confirmations_by_txid(self, block_hash: str) -> int:
        """Get confirmation count for a block."""
        result = self._rpc_request("block_info", hash=block_hash)
        if "error" in result:
            return 0
        confirmed = result.get("confirmed", "false") == "true"
        return 1 if confirmed else 0

    def mkpayout(self, destination: str, amount: Decimal, fee=0, subtract_fee_from_amount=False) -> dict:
        """
        Send Nano to a destination address.

        Builds and signs the block locally, then broadcasts via RPC.
        """
        try:
            # Find an account with sufficient balance
            addresses = self._get_addresses_json()
            source_address = None
            source_balance_raw = 0

            for address in addresses.keys():
                result = self._rpc_request("account_balance", account=address)
                if "error" not in result:
                    balance = raw_to_nano(result.get("balance", "0"))
                    if balance >= amount:
                        source_address = address
                        source_balance_raw = int(result.get("balance", "0"))
                        break

            if not source_address:
                return {"result": None, "error": {"message": "Insufficient balance in any account"}}

            # Get account info for frontier
            account_info = self._rpc_request("account_info", account=source_address)
            if "error" in account_info:
                return {"result": None, "error": {"message": f"Account not found: {account_info['error']}"}}

            frontier = account_info.get("frontier", "0" * 64)
            current_balance_raw = int(account_info.get("balance", "0"))

            # Calculate amount in raw
            amount_raw = nano_to_raw(amount)

            if current_balance_raw < amount_raw:
                return {"result": None, "error": {"message": "Insufficient balance"}}

            # Get private key for signing
            private_key = self._get_private_key_for_address(source_address)
            if not private_key:
                return {"result": None, "error": {"message": "Private key not found for address"}}

            # Generate work
            work = self._generate_work(frontier)
            if not work:
                return {"result": None, "error": {"message": "Failed to generate work"}}

            # Create nanopy Account and set it up
            account = nanopy.Account()
            account.sk = private_key.lower()  # nanopy expects lowercase hex

            # Set account state from network (normalize to lowercase)
            account.frontier = frontier.lower()
            account.raw_bal = current_balance_raw

            # Set representative
            rep_account = nanopy.Account(addr=self.NANO_REPRESENTATIVE)
            account.rep = rep_account

            # Create destination account
            dest_account = nanopy.Account(addr=destination)

            # Use nanopy Account.send() to create signed block
            state_block = account.send(
                to=dest_account,
                raw_amt=amount_raw,
                work=work
            )

            # Convert to dict for RPC
            block_json = json.loads(state_block.json)

            # Broadcast the block
            process_result = self._rpc_request(
                "process",
                json_block="true",
                subtype="send",
                block=block_json
            )

            if "error" in process_result:
                return {"result": None, "error": {"message": process_result["error"]}}

            block_hash = process_result.get("hash")
            if not block_hash:
                return {"result": None, "error": {"message": "No block hash returned"}}

            app.logger.info(f"Sent {amount} XNO to {destination}, block: {block_hash}")
            return {"result": block_hash, "error": None}

        except Exception as e:
            app.logger.exception(f"Failed to send {amount} XNO to {destination}")
            return {"result": None, "error": {"message": str(e)}}

    # Public PoW servers for work generation
    POW_SERVERS = [
        {"name": "XNOPay UK 1", "url": "https://uk1.public.xnopay.com/proxy"},
        {"name": "Rainstorm City", "url": "https://rainstorm.city/api"},
        {"name": "NanOslo", "url": "https://nanoslo.0x.no/proxy"},
    ]

    # Nano difficulty thresholds
    SEND_DIFFICULTY = "fffffff800000000"
    RECEIVE_DIFFICULTY = "fffffe0000000000"

    def _generate_work(self, hash_value: str, difficulty: str = None) -> Optional[str]:
        """
        Generate proof of work for a block.

        Fallback strategy:
        1. Try public PoW servers (pool)
        2. Try local node's work_generate if enabled
        3. Use nanopy's CPU-based work generation
        4. Fail safely
        """
        if difficulty is None:
            difficulty = self.SEND_DIFFICULTY

        # 1. Try public PoW servers first
        work = self._try_public_pow_servers(hash_value, difficulty)
        if work:
            return work

        # 2. Try local node's work_generate
        work = self._try_local_work_generate(hash_value, difficulty)
        if work:
            return work

        # 3. Use nanopy's CPU-based work generation as last resort
        work = self._try_nanopy_cpu_work(hash_value, difficulty)
        if work:
            return work

        # 4. Failed completely
        app.logger.error(f"All work generation methods failed for hash {hash_value}")
        return None

    def _try_public_pow_servers(self, hash_value: str, difficulty: str) -> Optional[str]:
        """Try generating work using public PoW servers."""
        for server in self.POW_SERVERS:
            try:
                app.logger.debug(f"Trying PoW server: {server['name']}")
                response = requests.post(
                    server["url"],
                    json={
                        "action": "work_generate",
                        "hash": hash_value,
                        "difficulty": difficulty
                    },
                    timeout=30
                )
                result = response.json()

                if "error" not in result and result.get("work"):
                    app.logger.info(f"Work generated by {server['name']}")
                    return result["work"]

                app.logger.debug(f"PoW server {server['name']} failed: {result.get('error', 'no work returned')}")

            except Exception as e:
                app.logger.debug(f"PoW server {server['name']} error: {e}")
                continue

        return None

    def _try_local_work_generate(self, hash_value: str, difficulty: str) -> Optional[str]:
        """Try generating work using the local Nano node."""
        try:
            result = self._rpc_request(
                "work_generate",
                hash=hash_value,
                difficulty=difficulty
            )
            if "error" not in result and result.get("work"):
                app.logger.info("Work generated by local node")
                return result["work"]

            # Check if work_generate is disabled
            if "error" in result:
                error_msg = str(result.get("error", "")).lower()
                if "disabled" in error_msg:
                    app.logger.debug("Local work generation is disabled")
                else:
                    app.logger.debug(f"Local work_generate error: {result['error']}")

        except Exception as e:
            app.logger.debug(f"Local work_generate failed: {e}")

        return None

    def _try_nanopy_cpu_work(self, hash_value: str, difficulty: str) -> Optional[str]:
        """Generate work using nanopy's CPU-based method (slowest but always works)."""
        try:
            app.logger.info(f"Generating work with CPU (this may take a while)...")

            # Create a dummy Account object for StateBlock
            dummy_acc = nanopy.Account()
            dummy_acc.addr = "nano_1111111111111111111111111111111111111111111111111111hifc8npp"

            # Create a minimal StateBlock with the hash we need work for
            # StateBlock.work_generate() computes work based on self.prev
            block = nanopy.StateBlock(
                acc=dummy_acc,
                rep=dummy_acc,
                bal=0,
                prev=hash_value,  # This is the hash we need work for
                link="0" * 64
            )

            # Generate work using CPU
            block.work_generate(difficulty)

            if block.work:
                app.logger.info(f"Work generated by CPU: {block.work}")
                return block.work

        except Exception as e:
            app.logger.error(f"CPU work generation failed: {e}")

        return None

    def create_wallet(self) -> dict:
        """
        Create a new wallet (generate seed) or verify existing one.
        """
        try:
            # Check if seed already exists
            existing_seed = self._get_seed()
            if existing_seed:
                addresses = self._get_addresses_json()
                if addresses:
                    app.logger.info(f"Using existing Nano wallet with {len(addresses)} addresses")
                    return {"error": None}
                else:
                    # Seed exists but no addresses, create first one
                    address = self.mkaddr()
                    app.logger.info(f"Created initial address for existing wallet: {address}")
                    return {"error": None}

            # Generate new seed
            seed = self._generate_seed()
            self._save_seed(seed)

            # Create first address
            address = self.mkaddr()
            app.logger.info(f"Created new Nano wallet with address: {address}")
            app.logger.warning("IMPORTANT: Backup your wallet using the dump_wallet function!")

            return {"error": None}

        except Exception as e:
            app.logger.exception("Failed to create Nano wallet")
            return {"error": str(e)}

    def dump_wallet(self):
        """
        Export the wallet seed for backup.

        WARNING: The seed can be used to restore all accounts. Keep it secure!
        """
        seed = self._get_seed()
        if not seed:
            return "shkeeper-nano-wallet.txt", "Error: No wallet seed found"

        try:
            now = datetime.datetime.now().strftime("%F_%T")
            filename = f"{now}_{self.crypto}_shkeeper_wallet.txt"

            addresses = self._get_addresses_json()

            lines = [
                f"Nano Wallet Backup - {now}",
                "",
                "SEED (KEEP THIS SECRET!):",
                seed,
                "",
                f"Addresses ({len(addresses)}):",
            ]

            for address, index in sorted(addresses.items(), key=lambda x: x[1]):
                lines.append(f"  [{index}] {address}")

            lines.append("")
            lines.append("To restore: Import this seed into any Nano wallet.")
            lines.append("Addresses are derived deterministically from the seed.")

            content = "\n".join(lines)
            return filename, content

        except Exception as e:
            app.logger.exception("Failed to dump Nano wallet")
            return "shkeeper-nano-wallet.txt", f"Error: {str(e)}"

    def get_all_addresses(self) -> List[str]:
        """Get all addresses managed by this wallet."""
        return list(self._get_addresses_json().keys())

    def receive_pending(self, address: str) -> List[str]:
        """
        Receive all pending blocks for an address.

        Returns list of received block hashes.
        """
        received_blocks = []

        try:
            # Get pending blocks
            result = self._rpc_request(
                "receivable",
                account=address,
                count="100"
            )

            pending_blocks = result.get("blocks", [])
            if isinstance(pending_blocks, dict):
                pending_blocks = list(pending_blocks.keys())

            if not pending_blocks:
                return []

            # Get account info
            account_info = self._rpc_request("account_info", account=address)
            if "error" in account_info:
                # Account not opened yet
                frontier = "0" * 64
                current_balance = 0
            else:
                frontier = account_info.get("frontier", "0" * 64)
                current_balance = int(account_info.get("balance", "0"))

            # Get private key and public key
            private_key = self._get_private_key_for_address(address)
            if not private_key:
                app.logger.error(f"Private key not found for {address}")
                return []

            public_key = self._get_public_key_for_address(address)
            if not public_key:
                app.logger.error(f"Public key not found for {address}")
                return []

            # Create nanopy Account and set it up
            account = nanopy.Account()
            account.sk = private_key.lower()  # nanopy expects lowercase hex

            # Set account state from network (normalize to lowercase)
            account.frontier = frontier.lower()
            account.raw_bal = current_balance

            # Set representative
            rep_account = nanopy.Account(addr=self.NANO_REPRESENTATIVE)
            account.rep = rep_account

            for block_hash in pending_blocks:
                try:
                    # Normalize block hash to lowercase (nanopy uses lowercase internally)
                    block_hash = block_hash.lower()

                    # Get block info to know the amount
                    block_info = self._rpc_request(
                        "block_info",
                        json_block="true",
                        hash=block_hash
                    )

                    if "error" in block_info:
                        continue

                    amount = int(block_info.get("amount", "0"))

                    # Determine work hash
                    # For unopened accounts, use public key; for existing accounts, use frontier
                    if account.frontier == "0" * 64:
                        work_hash = public_key.lower()
                    else:
                        work_hash = account.frontier.lower()

                    # Generate work (receive blocks use lower difficulty)
                    work = self._generate_work(work_hash, self.RECEIVE_DIFFICULTY)
                    if not work:
                        app.logger.error(f"Failed to generate work for receiving block {block_hash}")
                        continue

                    # Use nanopy Account.receive() to create signed block
                    state_block = account.receive(
                        digest=block_hash,
                        raw_amt=amount,
                        work=work
                    )

                    # Convert to dict for RPC
                    block_json = json.loads(state_block.json)

                    # Broadcast
                    process_result = self._rpc_request(
                        "process",
                        json_block="true",
                        subtype="receive",
                        block=block_json
                    )

                    if "hash" in process_result:
                        received_blocks.append(process_result["hash"])
                        app.logger.info(f"Received {raw_to_nano(amount)} XNO to {address}")
                    elif "error" in process_result:
                        app.logger.error(f"Failed to process receive block: {process_result['error']}")

                except Exception as e:
                    app.logger.error(f"Failed to receive block {block_hash}: {e}")
                    continue

        except Exception as e:
            app.logger.exception(f"Failed to receive pending for {address}")

        return received_blocks

    def receive_all_pending(self) -> int:
        """Receive pending blocks for all addresses."""
        total_received = 0
        for address in self.get_all_addresses():
            received = self.receive_pending(address)
            total_received += len(received)
        return total_received

    @property
    def wallet(self):
        return self._wallet.query.filter_by(crypto=self.crypto).first()
