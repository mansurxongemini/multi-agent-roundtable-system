"""
Transparent symmetric encryption for sensitive columns (provider API keys).

Values are encrypted with Fernet (AES-128-CBC + HMAC) before hitting the
database and decrypted on the way out, so plaintext secrets never live at rest.
The key is supplied via the FERNET_KEY environment variable / Django setting.

NOTE: API keys are decrypted ONLY inside the backend. They are never serialized
to the frontend (see api/serializers.py, which exposes a masked boolean only).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

_PREFIX = "enc::"  # marks an already-encrypted payload to keep operations idempotent


def _get_cipher() -> Fernet:
    key = getattr(settings, "FERNET_KEY", "") or ""
    if not key:
        raise ImproperlyConfigured(
            "FERNET_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and put it in your .env."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedTextField(models.TextField):
    """A TextField whose contents are encrypted at rest."""

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        if isinstance(value, str) and value.startswith(_PREFIX):
            return value  # already encrypted; do not double-encrypt
        token = _get_cipher().encrypt(value.encode()).decode()
        return _PREFIX + token

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        # Called during deserialization / form cleaning.
        if value is None:
            return value
        if isinstance(value, str) and value.startswith(_PREFIX):
            return self._decrypt(value)
        return value

    @staticmethod
    def _decrypt(value):
        if value is None or value == "":
            return value
        if not (isinstance(value, str) and value.startswith(_PREFIX)):
            # Legacy / plaintext value — return as-is for forward compatibility.
            return value
        token = value[len(_PREFIX):]
        try:
            return _get_cipher().decrypt(token.encode()).decode()
        except InvalidToken:
            # Wrong/rotated key — fail closed rather than leaking ciphertext.
            return ""
