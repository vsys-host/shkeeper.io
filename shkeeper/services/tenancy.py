from flask import g, has_request_context

from shkeeper.models import Store, UserRole, StoreWalletStatus


def get_current_store():
    if has_request_context() and getattr(g, "current_store", None):
        return g.current_store
    return None


def get_current_store_id():
    store = get_current_store()
    return store.id if store else None


def is_admin_user(user=None):
    user = user or getattr(g, "user", None)
    if not user:
        return False
    return user.role == UserRole.ADMIN


def invoice_query_for_user(query, user=None):
    user = user or getattr(g, "user", None)
    if not user:
        return query.filter(False)
    if user.role == UserRole.ADMIN:
        return query
    return query.filter_by(store_id=user.store_id)


def payout_query_for_user(query, user=None):
    return invoice_query_for_user(query, user=user)


def require_admin(user=None):
    if not is_admin_user(user):
        from werkzeug.exceptions import abort

        abort(403)


def store_owner_wallet(crypto_name):
    user = getattr(g, "user", None)
    if not user or user.role != UserRole.STORE_OWNER:
        return None
    store = getattr(g, "current_store", None)
    if not store:
        return None
    from shkeeper.services.store_service import get_store_wallet

    sw = get_store_wallet(store, crypto_name)
    if not sw or sw.status != StoreWalletStatus.READY:
        return None
    return sw


def api_key_for_session(crypto=None):
    user = getattr(g, "user", None)
    store = getattr(g, "current_store", None)
    if user and store and user.role == UserRole.STORE_OWNER:
        return store.api_key
    if crypto:
        return crypto.wallet.apikey
    return None
