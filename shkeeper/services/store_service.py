import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation

from flask import current_app as app

from shkeeper import db
from shkeeper.models import (
    Invoice,
    Store,
    StoreStatus,
    StoreWallet,
    StoreWalletStatus,
    User,
    UserRole,
    Wallet,
)
from shkeeper.modules.classes.crypto import Crypto
from shkeeper.modules.classes.tron_token import TronToken
from shkeeper.services.multistore import (
    DEFAULT_STORE_NAME,
    crypto_supports_multistore,
    filter_multistore_cryptos,
    is_multistore_backend,
    store_wallet_is_ready,
    uses_fee_deposit_account,
)

DEFAULT_ADMIN_STORE_ID = 1


def ensure_default_store():
    store = Store.query.filter_by(is_default=True).first()
    if store:
        if store.id != DEFAULT_ADMIN_STORE_ID:
            raise RuntimeError(
                "Default store must have id=1. "
                f"Found default store id={store.id}."
            )
        if _link_default_store_wallets(store):
            db.session.commit()
        return store

    existing_id_one = Store.query.get(DEFAULT_ADMIN_STORE_ID)
    if existing_id_one and not existing_id_one.is_default:
        raise RuntimeError(
            "Cannot create default store with id=1 because this id is already "
            "occupied by a non-default store."
        )

    store = Store(
        id=DEFAULT_ADMIN_STORE_ID,
        name=DEFAULT_STORE_NAME,
        api_key=_legacy_api_key(),
        platform_fee_percent=Decimal("0"),
        status=StoreStatus.ACTIVE,
        is_default=True,
    )
    db.session.add(store)
    db.session.flush()

    admin = User.query.get(1)
    if admin:
        admin.store_id = store.id
        admin.role = UserRole.ADMIN

    for invoice in Invoice.query.filter(Invoice.store_id.is_(None)).all():
        invoice.store_id = store.id

    for wallet in Wallet.query.all():
        if wallet.apikey and wallet.apikey != store.api_key:
            continue
        wallet.apikey = store.api_key

    _link_default_store_wallets(store)
    db.session.commit()
    app.logger.info("Created default store id=%s", store.id)
    return store


def _link_default_store_wallets(store: Store) -> bool:
    changed = False
    for crypto_name in filter_multistore_cryptos(Crypto.instances.keys()):
        crypto = Crypto.instances.get(crypto_name)
        if not is_multistore_backend(crypto):
            continue
        sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()
        if store_wallet_is_ready(sw, crypto):
            continue
        if not sw:
            sw = StoreWallet(
                store_id=store.id,
                crypto=crypto_name,
                status=StoreWalletStatus.PENDING,
            )
            db.session.add(sw)
            changed = True
        try:
            if uses_fee_deposit_account(crypto):
                sw.fda_address = crypto.fee_deposit_account_for(store_id=store.id).addr
            else:
                # UTXO has no FDA; the HD wallet is created lazily on first mkaddr.
                sw.fda_address = None
            sw.status = StoreWalletStatus.READY
            sw.last_error = None
            changed = True
        except Exception as exc:
            sw.status = StoreWalletStatus.FAILED
            sw.last_error = str(exc)
            changed = True
    return changed


def _legacy_api_key():
    wallet = Wallet.query.filter(Wallet.apikey.isnot(None)).first()
    if wallet and wallet.apikey:
        return wallet.apikey
    return app.config.get("SUGGESTED_WALLET_APIKEY") or secrets.token_urlsafe(16)


def resolve_store_by_api_key(api_key: str):
    store = Store.query.filter_by(api_key=api_key, status=StoreStatus.ACTIVE).first()
    if store:
        return store
    wallet = Wallet.query.filter_by(apikey=api_key).first()
    if wallet:
        default = ensure_default_store()
        return default
    return None

def create_store(name: str, platform_fee_percent=Decimal("0")):
    name = (name or "").strip()
    if not name:
        raise ValueError("Store name is required")
    try:
        platform_fee_percent = Decimal(platform_fee_percent)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid platform fee percent") from exc
    store = Store(
        name=name,
        api_key=secrets.token_urlsafe(24),
        platform_fee_percent=platform_fee_percent,
        status=StoreStatus.ACTIVE,
        is_default=False,
    )
    db.session.add(store)
    db.session.commit()
    provision_store_wallets(store)
    return store

def update_store(store: Store, *, name=None, platform_fee_percent=None):
    if store.is_default:
        raise ValueError("Default store settings cannot be changed")
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("Store name is required")
        store.name = name
    if platform_fee_percent is not None:
        try:
            store.platform_fee_percent = Decimal(platform_fee_percent)
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("Invalid platform fee percent") from exc
    db.session.commit()
    return store


def set_store_status(store: Store, status: StoreStatus):
    if store.is_default and status != StoreStatus.ACTIVE:
        raise ValueError("Default store cannot be suspended or deleted")
    if status not in (StoreStatus.ACTIVE, StoreStatus.SUSPENDED, StoreStatus.DELETED):
        raise ValueError(f"Unsupported store status: {status}")
    store.status = status
    db.session.commit()
    return store

def provision_store_wallets(store: Store, cryptos=None):
    cryptos = cryptos or filter_multistore_cryptos(Crypto.instances.keys())
    target_networks = set()
    for crypto_name in cryptos:
        if not crypto_supports_multistore(crypto_name):
            continue
        crypto = Crypto.instances.get(crypto_name)
        if not is_multistore_backend(crypto):
            continue
        target_networks.add(crypto.network_currency)
        sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()
        if not sw:
            sw = StoreWallet(
                store_id=store.id,
                crypto=crypto_name,
                status=StoreWalletStatus.PENDING,
            )
            db.session.add(sw)
    db.session.commit()

    # One FDA create per network (ETH/BNB/...), then attach all tokens on that network.
    by_network = {}
    for sw in StoreWallet.query.filter_by(store_id=store.id).all():
        crypto = Crypto.instances.get(sw.crypto)
        if not is_multistore_backend(crypto):
            continue
        if crypto.network_currency not in target_networks:
            continue
        by_network.setdefault(crypto.network_currency, []).append((sw, crypto))

    for network, items in by_network.items():
        try:
            _provision_network(store, network, items)
        except Exception as exc:
            app.logger.exception(
                "Provisioning failed store=%s network=%s: %s",
                store.id,
                network,
                exc,
            )
            for sw, crypto in items:
                if not store_wallet_is_ready(sw, crypto):
                    sw.status = StoreWalletStatus.FAILED
                    sw.last_error = str(exc)
            db.session.commit()

    _reconcile_store_fda_addresses(store)


def provision_crypto_for_all_stores(crypto_name: str):
    """Backfill StoreWallet + FDA for an already-created store when a crypto is enabled later."""
    if not crypto_supports_multistore(crypto_name):
        return
    crypto = Crypto.instances.get(crypto_name)
    if not is_multistore_backend(crypto):
        return

    # Default store FDA uses store_id=1 (same as Store.id).
    default = Store.query.filter_by(is_default=True).first()
    if default:
        _link_default_store_wallets(default)
        db.session.commit()

    stores = Store.query.filter(
        Store.is_default.is_(False),
        Store.status == StoreStatus.ACTIVE,
    ).all()
    # Provision the whole network group (e.g. OPETH + OP-USDC), not only the toggled crypto.
    related = [
        name
        for name in filter_multistore_cryptos(Crypto.instances.keys())
        if Crypto.instances.get(name)
        and is_multistore_backend(Crypto.instances[name])
        and Crypto.instances[name].network_currency == crypto.network_currency
    ]
    for store in stores:
        try:
            provision_store_wallets(store, cryptos=related)
        except Exception:
            app.logger.exception(
                "Failed to provision %s for store id=%s", crypto_name, store.id
            )


def ensure_store_wallets_provisioned(store: Store):
    """Create missing StoreWallet/FDA rows for currently available multistore cryptos."""
    if store.is_default:
        if _link_default_store_wallets(store):
            db.session.commit()
        return

    available = filter_multistore_cryptos(Crypto.instances.keys())
    wallets = StoreWallet.query.filter_by(store_id=store.id).all()
    existing = {sw.crypto for sw in wallets}
    missing = [name for name in available if name not in existing]
    incomplete = [
        sw.crypto
        for sw in wallets
        if sw.crypto in available
        and not store_wallet_is_ready(sw, Crypto.instances.get(sw.crypto))
    ]
    to_provision = list(dict.fromkeys([*missing, *incomplete]))
    if not to_provision:
        # Still reconcile so token FDAs on a network stay aligned.
        _reconcile_store_fda_addresses(store)
        return
    provision_store_wallets(store, cryptos=to_provision)

def retry_provisioning(store: Store, crypto_name: str):
    """Retry FDA provisioning for one crypto — one FDA per store per network."""
    sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first_or_404()
    crypto = Crypto.instances.get(crypto_name)
    if not is_multistore_backend(crypto):
        raise ValueError(f"{crypto_name} does not support multistore")

    sw.status = StoreWalletStatus.PENDING
    sw.last_error = None
    db.session.commit()

    # Retry the whole network group so ETH-USDC/USDT share one create, not N races.
    items = []
    for other in StoreWallet.query.filter_by(store_id=store.id).all():
        other_crypto = Crypto.instances.get(other.crypto)
        if (
            other_crypto
            and is_multistore_backend(other_crypto)
            and other_crypto.network_currency == crypto.network_currency
        ):
            other.status = StoreWalletStatus.PENDING
            items.append((other, other_crypto))
    db.session.commit()

    try:
        _provision_network(store, crypto.network_currency, items)
        _reconcile_store_fda_addresses(store)
    except Exception as exc:
        app.logger.exception(
            "Retry provisioning failed store=%s crypto=%s: %s",
            store.id,
            crypto_name,
            exc,
        )
        for other, other_crypto in items:
            if not store_wallet_is_ready(other, other_crypto):
                other.status = StoreWalletStatus.FAILED
                other.last_error = str(exc)
        db.session.commit()
        raise

def _provision_network(store: Store, network: str, items):
    """Ensure a single FDA for store+network (ETH-like) or mark UTXO wallets ready."""
    if not items:
        return

    crypto = items[0][1]

    if not uses_fee_deposit_account(crypto):
        for sw, _ in items:
            sw.fda_address = None
            sw.status = StoreWalletStatus.READY
            sw.last_error = None
        db.session.commit()
        return

    existing_addr = next(
        (sw.fda_address for sw, _ in items if sw.fda_address),
        None,
    )
    if not existing_addr:
        for other in StoreWallet.query.filter_by(store_id=store.id).all():
            other_crypto = Crypto.instances.get(other.crypto)
            if (
                other.fda_address
                and other_crypto
                and is_multistore_backend(other_crypto)
                and other_crypto.network_currency == network
            ):
                existing_addr = other.fda_address
                break

    address = existing_addr or crypto.create_fee_deposit_account(store_id=store.id)

    for sw, _ in items:
        sw.fda_address = address
        sw.status = StoreWalletStatus.READY
        sw.last_error = None
    db.session.commit()


def _reconcile_store_fda_addresses(store: Store):
    """Ensure all wallets on the same network share one FDA address."""
    by_network = {}
    for sw in StoreWallet.query.filter_by(store_id=store.id).all():
        crypto = Crypto.instances.get(sw.crypto)
        if not is_multistore_backend(crypto):
            continue
        network = crypto.network_currency
        by_network.setdefault(network, []).append((sw, crypto))

    changed = False
    for network, items in by_network.items():
        if items and not uses_fee_deposit_account(items[0][1]):
            continue
        canonical = next(
            (sw for sw, _ in items if sw.fda_address and sw.status == StoreWalletStatus.READY),
            None,
        )
        if not canonical:
            continue
        canonical_addr = canonical.fda_address

        for sw, _ in items:
            if sw.fda_address != canonical_addr:
                sw.fda_address = canonical_addr
                if sw.status != StoreWalletStatus.FAILED:
                    sw.status = StoreWalletStatus.READY
                    sw.last_error = None
                changed = True

    if changed:
        db.session.commit()

def get_store_wallet(store: Store, crypto_name: str):
    return StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()


def store_wallet_balance(store: Store, crypto_name: str, sw: StoreWallet = None):
    crypto = Crypto.instances.get(crypto_name)
    if not is_multistore_backend(crypto):
        return None

    sw = sw or get_store_wallet(store, crypto_name)
    if store_wallet_is_ready(sw, crypto):
        return crypto.balance_for_account(store_id=store.id)

    # Default store native coin: fall back to store_id=1 FDA when not linked yet.
    if store.is_default and crypto.crypto == crypto.network_currency:
        return crypto.balance(store_id=store.id)

    return None


def store_balances_map(stores, crypto_names):
    """Fetch balances for many stores/cryptos with one wallet query + parallel HTTP.
    Keeps the existing per-crypto /balance sidecar API unchanged.
    """
    result = {store.id: {name: None for name in crypto_names} for store in stores}
    if not stores or not crypto_names:
        return result

    store_by_id = {store.id: store for store in stores}
    wallets = StoreWallet.query.filter(
        StoreWallet.store_id.in_(store_by_id.keys()),
        StoreWallet.crypto.in_(list(crypto_names)),
    ).all()
    wallet_by_key = {(sw.store_id, sw.crypto): sw for sw in wallets}

    jobs = []
    for store in stores:
        for crypto_name in crypto_names:
            sw = wallet_by_key.get((store.id, crypto_name))
            crypto = Crypto.instances.get(crypto_name)
            if not is_multistore_backend(crypto):
                continue
            if store_wallet_is_ready(sw, crypto) or (
                store.is_default and crypto.crypto == crypto.network_currency
            ):
                jobs.append((store.id, crypto_name))

    if not jobs:
        return result

    app_obj = app._get_current_object()

    def _fetch(job):
        store_id, crypto_name = job
        crypto = Crypto.instances[crypto_name]
        with app_obj.app_context():
            try:
                balance = crypto.balance(store_id=store_id)
            except Exception as exc:
                app_obj.logger.warning(
                    "Balance fetch failed store=%s crypto=%s: %s",
                    store_id,
                    crypto_name,
                    exc,
                )
                balance = None
        return store_id, crypto_name, balance

    workers = min(16, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_fetch, job) for job in jobs]
        for fut in as_completed(futures):
            store_id, crypto_name, balance = fut.result()
            result[store_id][crypto_name] = balance

    return result


def cryptos_for_store(store: Store):
    wallets = StoreWallet.query.filter_by(
        store_id=store.id, status=StoreWalletStatus.READY
    ).all()
    return [
        Crypto.instances[sw.crypto]
        for sw in wallets
        if sw.crypto in Crypto.instances
    ]


def crypto_balance_for_session(crypto_name: str, user=None, store=None):
    from flask import g

    from shkeeper.models import UserRole

    user = user or getattr(g, "user", None)
    store = store or getattr(g, "current_store", None)
    crypto = Crypto.instances.get(crypto_name)
    if not crypto:
        return None

    if user and user.role == UserRole.STORE_OWNER and store:
        balance = store_wallet_balance(store, crypto_name)
        return balance if balance is not None else Decimal(0)

    return crypto.balance()


def effective_fee_percent(store: Store, sw: StoreWallet):
    if sw and sw.fee_percent_override is not None:
        return Decimal(sw.fee_percent_override)
    return Decimal(store.platform_fee_percent or 0)


def fee_collection_setting_name(crypto_name: str) -> str:
    return f"fee_collection_{crypto_name}"


_TRON_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_TRON_MULTISTORE = frozenset({"TRX", "USDT", "USDC"})


def _is_tron_like(crypto_name: str) -> bool:
    crypto = Crypto.instances.get(crypto_name)
    if crypto is not None:
        return isinstance(crypto, TronToken)
    return crypto_name in _TRON_MULTISTORE


def _address_key(crypto_name: str, address: str) -> str:
    """Compare-key for fee-collection addresses. Tron is case-sensitive (base58)."""
    address = (address or "").strip()
    if _is_tron_like(crypto_name):
        return address
    return address.lower()


def _is_valid_eth_address(address: str) -> bool:
    if not address or not address.startswith(("0x", "0X")) or len(address) != 42:
        return False
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


def _is_valid_utxo_address(address: str, crypto_name: str | None = None) -> bool:
    # BTC/LTC/DOGE: do not second-guess the destination; the operator owns the risk.
    return bool(address)


def _is_valid_tron_address(address: str) -> bool:
    if not address or len(address) != 34 or not address.startswith("T"):
        return False
    return all(ch in _TRON_B58_ALPHABET for ch in address)


def _is_utxo_like(crypto_name: str) -> bool:
    from shkeeper.modules.classes.utxo_like_wallet_crypto import UtxoLikeWalletCrypto

    crypto = Crypto.instances.get(crypto_name)
    if crypto is not None:
        return isinstance(crypto, UtxoLikeWalletCrypto)
    return crypto_name in ("BTC", "LTC", "DOGE")


def _is_valid_fee_collection_format(crypto_name: str, address: str) -> bool:
    if _is_utxo_like(crypto_name):
        return _is_valid_utxo_address(address, crypto_name)
    if _is_tron_like(crypto_name):
        return _is_valid_tron_address(address)
    return _is_valid_eth_address(address)


def _known_fda_addresses(crypto_name: str) -> set[str]:
    """FDA addresses known to shkeeper for this crypto (DB + default sidecar FDA)."""
    crypto = Crypto.instances.get(crypto_name)
    if not uses_fee_deposit_account(crypto):
        return set()
    addrs = {
        _address_key(crypto_name, sw.fda_address)
        for sw in StoreWallet.query.filter(
            StoreWallet.crypto == crypto_name,
            StoreWallet.fda_address.isnot(None),
        ).all()
        if sw.fda_address
    }
    try:
        fda = crypto.fee_deposit_account_for(store_id=1)
        if fda and fda.addr:
            addrs.add(_address_key(crypto_name, fda.addr))
    except Exception as exc:
        app.logger.warning(
            "Could not load default FDA for %s during fee-collection validation: %s",
            crypto_name,
            exc,
        )
    return addrs


def _sidecar_managed_addresses(crypto_name: str) -> set[str]:
    """All addresses tracked by the ETH/Tron sidecar for this crypto."""
    crypto = Crypto.instances.get(crypto_name)
    if not uses_fee_deposit_account(crypto):
        return set()
    store_ids = {1}
    store_ids.update(
        sw.store_id
        for sw in StoreWallet.query.filter_by(crypto=crypto_name).all()
        if sw.store_id
    )
    addrs: set[str] = set()
    for store_id in store_ids:
        response = crypto.get_all_addresses(store_id=store_id)
        if isinstance(response, dict) and response.get("status") == "error":
            raise ValueError(
                response.get("msg")
                or f"Cannot list addresses for {crypto_name}"
            )
        if not isinstance(response, list):
            raise ValueError(f"Unexpected address list for {crypto_name}")
        addrs.update(_address_key(crypto_name, addr) for addr in response if addr)
    return addrs


def validate_fee_collection_address(crypto_name: str, address: str | None) -> str | None:
    """Validate an admin wallet (stored as fee_collection_address).

    ETH/Tron: must be external or an FDA — not a generated invoice/hot address.
    BTC/LTC/DOGE: any non-empty destination is stored as-is.
    """
    address = (address or "").strip() or None
    if not address:
        return None
    if not _is_valid_fee_collection_format(crypto_name, address):
        if _is_tron_like(crypto_name):
            family = "TRON"
        elif _is_utxo_like(crypto_name):
            family = crypto_name
        else:
            family = "Ethereum"
        raise ValueError(f"Invalid {family} address: {address}")

    if _is_utxo_like(crypto_name):
        return address

    key = _address_key(crypto_name, address)
    if key in _known_fda_addresses(crypto_name):
        return address

    try:
        managed = _sidecar_managed_addresses(crypto_name)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Cannot validate admin wallet: sidecar unavailable ({exc})"
        ) from exc

    if key in managed:
        raise ValueError(
            "admin wallet must be an external address or a fee-deposit "
            "(FDA) address, not a generated invoice/hot address"
        )
    return address


def get_global_fee_collection_address(crypto_name: str):
    from shkeeper.models import Setting

    setting = Setting.query.get(fee_collection_setting_name(crypto_name))
    if setting and setting.value:
        return setting.value
    return None


def set_global_fee_collection_address(
    crypto_name: str, address: str | None, *, skip_validation: bool = False
):
    from shkeeper.models import Setting

    key = fee_collection_setting_name(crypto_name)
    setting = Setting.query.get(key)
    if skip_validation:
        address = (address or "").strip() or None
    else:
        address = validate_fee_collection_address(crypto_name, address)
    if not address:
        if setting:
            db.session.delete(setting)
            db.session.commit()
        return None
    if not setting:
        setting = Setting(name=key, value=address)
        db.session.add(setting)
    else:
        setting.value = address
    db.session.commit()
    return address


def fee_collection_address(store: Store, sw: StoreWallet, crypto_name: str):
    if sw and sw.fee_collection_address:
        return sw.fee_collection_address

    global_addr = get_global_fee_collection_address(crypto_name)
    if global_addr:
        return global_addr

    default_store = Store.query.filter_by(is_default=True).first()
    if default_store and default_store.id != store.id:
        global_sw = StoreWallet.query.filter_by(
            store_id=default_store.id, crypto=crypto_name
        ).first()
        if global_sw and global_sw.fee_collection_address:
            return global_sw.fee_collection_address
    return None


def store_api_key_for_invoice(invoice):
    if invoice.store_id:
        store = Store.query.get(invoice.store_id)
        if store:
            return store.api_key
    return None


def get_store_users(store: Store):
    return User.query.filter_by(store_id=store.id, role=UserRole.STORE_OWNER).all()


def create_store_owner(store: Store, username: str, password: str):
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required")
    if not password:
        raise ValueError("Password is required")
    if store.is_default:
        raise ValueError(
            "Cannot add store owners to the Default store. Create a separate store for the merchant."
        )
    if get_store_users(store):
        raise ValueError("This store already has an owner account.")
    if User.query.filter_by(username=username).first():
        raise ValueError(f"Username {username!r} is already taken")
    user = User(
        username=username,
        passhash=User.get_password_hash(password),
        store_id=store.id,
        role=UserRole.STORE_OWNER,
    )
    db.session.add(user)
    db.session.commit()
    return user
