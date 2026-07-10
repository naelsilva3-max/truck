"""
EncryptedBinaryField — transparently encrypts/decrypts bytes at rest.

Used for biometric templates (LGPD: fingerprint data is sensitive personal
data and must not sit in the database as plaintext).
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    return Fernet(settings.BIOMETRIC_ENCRYPTION_KEY)


class EncryptedBinaryField(models.BinaryField):
    """A BinaryField that encrypts on write and decrypts on read via Fernet
    (AES-128-CBC + HMAC-SHA256, authenticated encryption).

    Rows written before this field was introduced are still plaintext in the
    database. `from_db_value` falls back to returning the raw bytes as-is
    when decryption fails (`InvalidToken`), so those legacy rows keep
    working — the data migration that ships alongside this field re-saves
    every existing row once, which encrypts them for good. New rows are
    always encrypted via `get_prep_value`.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None:
            return value
        return _fernet().encrypt(bytes(value))

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        raw = bytes(value)
        try:
            return _fernet().decrypt(raw)
        except InvalidToken:
            return raw
