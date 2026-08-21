from flask import g

from shkeeper.models import UserRole, StoreWalletStatus


def is_admin_user(user=None):
    user = user or getattr(g, "user", None)
    if not user:
        return False
    return user.role == UserRole.ADMIN


def require_admin(user=None):
    if not is_admin_user(user):
        from werkzeug.exceptions import abort

        abort(403)


def store_owner_wallet(crypto_name):
    user = getattr(g, "user", None)
    if not user or user.role != UserRole.STORE_OWNER:
        return None
    return current_store_wallet(crypto_name)


def current_store_wallet(crypto_name):
    """READY StoreWallet for g.current_store (session or API-key auth)."""
    store = getattr(g, "current_store", None)
    if not store:
        return None
    from shkeeper.services.store_service import get_store_wallet

    sw = get_store_wallet(store, crypto_name)
    if not sw or sw.status != StoreWalletStatus.READY:
        return None
    return sw


def require_default_store(store=None):
    store = store or getattr(g, "current_store", None)
    if not store or not store.is_default:
        from werkzeug.exceptions import abort

        abort(403)


def api_key_for_session(crypto=None):
    user = getattr(g, "user", None)
    store = getattr(g, "current_store", None)
    if user and store and user.role == UserRole.STORE_OWNER:
        return store.api_key
    if crypto:
        return crypto.wallet.apikey
    return None
