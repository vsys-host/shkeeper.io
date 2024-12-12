import base64
import enum
from time import sleep

import bcrypt

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class WalletEncryptionPersistentStatus(enum.Enum):
    pending = enum.auto()
    disabled = enum.auto()
    enabled = enum.auto()


class WalletEncryptionRuntimeStatus(enum.Enum):
    pending = enum.auto()
    fail = enum.auto()
    success = enum.auto()


class wallet_encryption:
    _key = "shkeeper"
    _runtime_status = WalletEncryptionRuntimeStatus.pending

    @staticmethod
    def persistent_status() -> WalletEncryptionPersistentStatus:
        from . import db
        from .models import Setting

        if setting := Setting.query.get("WalletEncryptionPersistentStatus"):
            return WalletEncryptionPersistentStatus(int(setting.value))

    @staticmethod
    def set_persistent_status(status: WalletEncryptionPersistentStatus):
        from . import db
        from .models import Setting

        if setting := Setting.query.get("WalletEncryptionPersistentStatus"):
            setting.value = status.value
        else:
            setting = Setting(
                name="WalletEncryptionPersistentStatus", value=status.value
            )
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

    @classmethod
    def fernet_key(cls):
        if not hasattr(cls, "_fernet_key"):
            salt = b"Shkeeper4TheWin!"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=500_000,
            )
            cls._fernet_key = base64.urlsafe_b64encode(kdf.derive(cls.key().encode()))
        return cls._fernet_key

    def get_hash(key):
        return bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=12))

    @staticmethod
    def verify_hash(key):
        return bcrypt.checkpw(key.encode(), wallet_encryption.retrieve_hash())

    def save_hash(hash):
        from . import db
        from .models import Setting

        if setting := Setting.query.get("WalletEncryptionPasswordHash"):
            setting.value = hash
        else:
            setting = Setting(name="WalletEncryptionPasswordHash", value=hash)
            db.session.add(setting)
        db.session.commit()

    @staticmethod
    def retrieve_hash():
        from .models import Setting

        if setting := Setting.query.get("WalletEncryptionPasswordHash"):
            return setting.value

    @staticmethod
    def wait_for_key():

        from flask import current_app as app

        PS = WalletEncryptionPersistentStatus
        RS = WalletEncryptionRuntimeStatus
        WE = wallet_encryption

        while WE.persistent_status() is PS.pending:
            sleep(1)
            app.logger.debug(
                "wait_for_key() is waiting for user to choose use encryption or not"
            )

        if WE.persistent_status() is PS.disabled:
            # return default key
            return WE.key()

        else:
            assert WE.persistent_status() is PS.enabled

            while WE.runtime_status() in (RS.pending, RS.fail):
                # wait for user to enter the key
                sleep(1)
                app.logger.debug("wait_for_key() is waiting for user to enter key")

            assert WE.runtime_status() is RS.success

            # return the user provided key
            return WE.key()

    @staticmethod
    def encrypt_text(cleartext: str):
        wallet_encryption.wait_for_key()
        return base64.urlsafe_b64encode(
            Fernet(wallet_encryption.fernet_key()).encrypt(cleartext.encode())
        ).decode()

    @staticmethod
    def decrypt_text(ciphertext: str):
        wallet_encryption.wait_for_key()
        return (
            Fernet(wallet_encryption.fernet_key())
            .decrypt(base64.urlsafe_b64decode(ciphertext))
            .decode()
        )
