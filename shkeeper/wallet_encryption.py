import enum

import bcrypt


class WalletEncryptionPersistentStatus(enum.Enum):
    pending = enum.auto()
    disabled = enum.auto()
    enabled = enum.auto()


class WalletEncryptionRuntimeStatus(enum.Enum):
    pending = enum.auto()
    fail = enum.auto()
    success = enum.auto()


class wallet_encryption:

    _key = 'shkeeper'
    _runtime_status = WalletEncryptionRuntimeStatus.pending

    @staticmethod
    def persistent_status() -> WalletEncryptionPersistentStatus:
        from . import db
        from .models import Setting
        if setting := Setting.query.get('WalletEncryptionPersistentStatus'):
            return WalletEncryptionPersistentStatus(int(setting.value))

    @staticmethod
    def set_persistent_status(status: WalletEncryptionPersistentStatus):
        from . import db
        from .models import Setting
        if setting := Setting.query.get('WalletEncryptionPersistentStatus'):
            setting.value = status.value
        else:
            setting = Setting(name='WalletEncryptionPersistentStatus', value=status.value)
            db.session.add(setting)
        db.session.commit()

    @classmethod
    def runtime_status(cls) -> WalletEncryptionRuntimeStatus:
        return cls._runtime_status

    @classmethod
    def set_runtime_status(cls, status: WalletEncryptionRuntimeStatus):
        cls._runtime_status = status

    @staticmethod
    def test_key(key):
        return wallet_encryption.verify_hash(key)

    @classmethod
    def key(cls):
        return cls._key

    @classmethod
    def set_key(cls, key):
        cls._key = key

    def get_hash(key):
        return bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=12))

    @staticmethod
    def verify_hash(key):
        return bcrypt.checkpw(key.encode(), wallet_encryption.retrieve_hash())

    def save_hash(hash):
        from . import db
        from .models import Setting
        if setting := Setting.query.get('WalletEncryptionPasswordHash'):
            setting.value = hash
        else:
            setting = Setting(name='WalletEncryptionPasswordHash', value=hash)
            db.session.add(setting)
        db.session.commit()

    @staticmethod
    def retrieve_hash():
        from .models import Setting
        if setting := Setting.query.get('WalletEncryptionPasswordHash'):
            return setting.value