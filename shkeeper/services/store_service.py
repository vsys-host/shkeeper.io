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
from shkeeper.modules.classes.ethereum import Ethereum
from shkeeper.services.multistore import (
    DEFAULT_STORE_NAME,
    crypto_supports_multistore,
    filter_multistore_cryptos,
)


def ensure_default_store():
    store = Store.query.filter_by(is_default=True).first()
    if store:
        if _link_default_store_wallets(store):
            db.session.commit()
        return store

    store = Store(
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
        if not crypto or not isinstance(crypto, Ethereum):
            continue
        sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()
        if (
            sw
            and sw.status == StoreWalletStatus.READY
            and sw.fda_address
            and sw.fda_key == "default"
        ):
            continue
        if not sw:
            sw = StoreWallet(
                store_id=store.id,
                crypto=crypto_name,
                fda_key="default",
                status=StoreWalletStatus.PENDING,
            )
            db.session.add(sw)
            changed = True
        try:
            fda = crypto.fee_deposit_account_for(fda_key="default")
            sw.fda_address = fda.addr
            sw.fda_key = "default"
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

def _fda_key(store_id: int, network: str) -> str:
    return f"store-{store_id}-{network}"

def create_store(name: str, platform_fee_percent=Decimal("0")):
    store = Store(
        name=name.strip(),
        api_key=secrets.token_urlsafe(24),
        platform_fee_percent=Decimal(platform_fee_percent),
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
        if not crypto or not isinstance(crypto, Ethereum):
            continue
        target_networks.add(crypto.network_currency)
        sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()
        shared_key = _fda_key(store.id, crypto.network_currency)
        if not sw:
            sw = StoreWallet(
                store_id=store.id,
                crypto=crypto_name,
                fda_key=shared_key,
                status=StoreWalletStatus.PENDING,
            )
            db.session.add(sw)
        else:
            sw.fda_key = shared_key
    db.session.commit()

    # One FDA create per network (ETH/BNB/...), then attach all tokens on that network.
    by_network = {}
    for sw in StoreWallet.query.filter_by(store_id=store.id).all():
        crypto = Crypto.instances.get(sw.crypto)
        if not crypto or not isinstance(crypto, Ethereum):
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
            for sw, _ in items:
                if sw.status != StoreWalletStatus.READY or not sw.fda_address:
                    sw.status = StoreWalletStatus.FAILED
                    sw.last_error = str(exc)
            db.session.commit()

    _reconcile_store_fda_addresses(store)


def provision_crypto_for_all_stores(crypto_name: str):
    """Backfill StoreWallet + FDA for an already-created store when a crypto is enabled later."""
    if not crypto_supports_multistore(crypto_name):
        return
    crypto = Crypto.instances.get(crypto_name)
    if not crypto or not isinstance(crypto, Ethereum):
        return

    # Default store uses the shared legacy FDA ("default"), not store-<id>-<network>.
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
        and isinstance(Crypto.instances[name], Ethereum)
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
        and (sw.status != StoreWalletStatus.READY or not sw.fda_address)
    ]
    to_provision = list(dict.fromkeys([*missing, *incomplete]))
    if not to_provision:
        # Still reconcile so token FDAs on a network stay aligned.
        _reconcile_store_fda_addresses(store)
        return
    provision_store_wallets(store, cryptos=to_provision)

def retry_provisioning(store: Store, crypto_name: str):
    """Retry FDA provisioning for one crypto — uses network key store-<id>-<network>."""
    sw = StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first_or_404()
    crypto = Crypto.instances.get(crypto_name)
    if not crypto or not isinstance(crypto, Ethereum):
        raise ValueError(f"{crypto_name} is not an ethereum-like crypto")

    shared_key = _fda_key(store.id, crypto.network_currency)
    sw.fda_key = shared_key
    sw.status = StoreWalletStatus.PENDING
    sw.last_error = None
    db.session.commit()

    # Retry the whole network group so ETH-USDC/USDT share one create, not N races.
    items = []
    for other in StoreWallet.query.filter_by(store_id=store.id).all():
        other_crypto = Crypto.instances.get(other.crypto)
        if (
            other_crypto
            and isinstance(other_crypto, Ethereum)
            and other_crypto.network_currency == crypto.network_currency
        ):
            other.fda_key = shared_key
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
        for other, _ in items:
            if other.status != StoreWalletStatus.READY or not other.fda_address:
                other.status = StoreWalletStatus.FAILED
                other.last_error = str(exc)
        db.session.commit()
        raise

def _provision_network(store: Store, network: str, items):
    """Ensure a single FDA for store+network and assign it to all wallets in items."""
    if not items:
        return

    shared_key = _fda_key(store.id, network)
    crypto = items[0][1]

    existing_addr = next(
        (sw.fda_address for sw, _ in items if sw.fda_address),
        None,
    )
    if not existing_addr:
        sibling = (
            StoreWallet.query.filter(
                StoreWallet.store_id == store.id,
                StoreWallet.fda_key == shared_key,
                StoreWallet.fda_address.isnot(None),
            ).first()
        )
        if sibling:
            existing_addr = sibling.fda_address

    if existing_addr:
        address = existing_addr
        # Ensure sidecar still has this key registered (idempotent).
        try:
            address = crypto.create_fee_deposit_account(fda_key=shared_key)
        except Exception:
            address = existing_addr
    else:
        address = crypto.create_fee_deposit_account(fda_key=shared_key)

    for sw, _ in items:
        sw.fda_key = shared_key
        sw.fda_address = address
        sw.status = StoreWalletStatus.READY
        sw.last_error = None
    db.session.commit()


def _provision_single_wallet(store: Store, sw: StoreWallet):
    crypto = Crypto.instances.get(sw.crypto)
    if not crypto or not isinstance(crypto, Ethereum):
        raise ValueError(f"{sw.crypto} is not an ethereum-like crypto")
    _provision_network(store, crypto.network_currency, [(sw, crypto)])


def _reconcile_store_fda_addresses(store: Store):
    """Ensure all wallets on the same network share one FDA address."""
    by_network = {}
    for sw in StoreWallet.query.filter_by(store_id=store.id).all():
        crypto = Crypto.instances.get(sw.crypto)
        if not crypto or not isinstance(crypto, Ethereum):
            continue
        network = crypto.network_currency
        shared_key = _fda_key(store.id, network)
        sw.fda_key = shared_key
        by_network.setdefault(network, []).append((sw, crypto))

    changed = False
    for network, items in by_network.items():
        shared_key = _fda_key(store.id, network)
        canonical = next(
            (sw for sw, _ in items if sw.fda_address and sw.status == StoreWalletStatus.READY),
            None,
        )
        if not canonical:
            continue
        # Prefer address already registered under the shared network key (idempotent).
        try:
            crypto = items[0][1]
            canonical_addr = crypto.create_fee_deposit_account(fda_key=shared_key)
        except Exception:
            canonical_addr = canonical.fda_address

        for sw, _ in items:
            if sw.fda_address != canonical_addr or sw.fda_key != shared_key:
                sw.fda_address = canonical_addr
                sw.fda_key = shared_key
                if sw.status != StoreWalletStatus.FAILED:
                    sw.status = StoreWalletStatus.READY
                    sw.last_error = None
                changed = True

    if changed:
        db.session.commit()


reconcile_store_fda_addresses = _reconcile_store_fda_addresses


def get_store_wallet(store: Store, crypto_name: str):
    return StoreWallet.query.filter_by(store_id=store.id, crypto=crypto_name).first()


def store_wallet_balance(store: Store, crypto_name: str, sw: StoreWallet = None):
    crypto = Crypto.instances.get(crypto_name)
    if not crypto or not isinstance(crypto, Ethereum):
        return None

    sw = sw or get_store_wallet(store, crypto_name)
    if sw and sw.fda_address:
        return crypto.balance_for_account(account=sw.fda_address)

    # Default store native coin uses the legacy global wallet when FDA is not linked yet.
    if store.is_default and crypto.crypto == crypto.network_currency:
        return crypto.balance()

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
            if not crypto or not isinstance(crypto, Ethereum):
                continue
            if sw and sw.fda_address:
                jobs.append((store.id, crypto_name, sw.fda_address, False))
            elif store.is_default and crypto.crypto == crypto.network_currency:
                jobs.append((store.id, crypto_name, None, True))

    if not jobs:
        return result

    app_obj = app._get_current_object()

    def _fetch(job):
        store_id, crypto_name, account, use_global = job
        crypto = Crypto.instances[crypto_name]
        with app_obj.app_context():
            try:
                if use_global:
                    balance = crypto.balance()
                else:
                    balance = crypto.balance_for_account(account=account)
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


def _is_valid_eth_address(address: str) -> bool:
    if not address or not address.startswith(("0x", "0X")) or len(address) != 42:
        return False
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


def _known_fda_addresses(crypto_name: str) -> set[str]:
    """FDA addresses known to shkeeper for this crypto (DB + default sidecar FDA)."""
    addrs = {
        sw.fda_address.lower()
        for sw in StoreWallet.query.filter(
            StoreWallet.crypto == crypto_name,
            StoreWallet.fda_address.isnot(None),
        ).all()
        if sw.fda_address
    }
    crypto = Crypto.instances.get(crypto_name)
    if crypto and isinstance(crypto, Ethereum):
        try:
            fda = crypto.fee_deposit_account_for(fda_key="default")
            if fda and fda.addr:
                addrs.add(fda.addr.lower())
        except Exception as exc:
            app.logger.warning(
                "Could not load default FDA for %s during fee-collection validation: %s",
                crypto_name,
                exc,
            )
    return addrs


def _sidecar_managed_addresses(crypto_name: str) -> set[str]:
    """All addresses tracked by the ethereum-like sidecar for this crypto."""
    crypto = Crypto.instances.get(crypto_name)
    if not crypto or not isinstance(crypto, Ethereum):
        return set()
    response = crypto.get_all_addresses()
    if isinstance(response, dict) and response.get("status") == "error":
        raise ValueError(
            response.get("msg")
            or f"Cannot list addresses for {crypto_name}"
        )
    if not isinstance(response, list):
        raise ValueError(f"Unexpected address list for {crypto_name}")
    return {addr.lower() for addr in response if addr}


def validate_fee_collection_address(crypto_name: str, address: str | None) -> str | None:
    """Fee collection must be external or an FDA — not a generated invoice address."""
    address = (address or "").strip() or None
    if not address:
        return None
    if not _is_valid_eth_address(address):
        raise ValueError(f"Invalid Ethereum address: {address}")

    lower = address.lower()
    if lower in _known_fda_addresses(crypto_name):
        return address

    try:
        managed = _sidecar_managed_addresses(crypto_name)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Cannot validate fee collection: sidecar unavailable ({exc})"
        ) from exc

    if lower in managed:
        raise ValueError(
            "fee collection must be an external address or a fee-deposit "
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
    username = username.strip()
    if not username:
        raise ValueError("Username is required")
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
