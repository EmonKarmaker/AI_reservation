"""Symmetric encryption for sensitive values stored in the database.

Used for:
- ``platform_settings.value_encrypted`` (e.g., the Groq API key)
- ``business_settings.custom_api_key_encrypted`` (per-tenant BYO Groq key)

The Fernet key lives in the ``PLATFORM_ENCRYPTION_KEY`` environment variable
and never touches the database. Rotating it requires re-encrypting every
affected row — do NOT rotate casually. See ``docs/06-env-vars.md``.

Public surface:

- ``platform_encryption`` — module-level singleton, the usual entrypoint
- ``PlatformEncryption`` — class form, useful in tests with a custom key
- ``EncryptionError`` — raised on bad key, corrupted ciphertext, etc.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""


class PlatformEncryption:
    """Thin wrapper around Fernet that reads the key from settings.

    Fernet ciphertext is URL-safe base64; storing it as ``text`` in Postgres
    is correct (no need for ``bytea``).
    """

    def __init__(self, key: str | bytes | None = None) -> None:
        actual_key = key if key is not None else settings.PLATFORM_ENCRYPTION_KEY
        try:
            self._fernet = Fernet(actual_key)
        except (ValueError, TypeError) as exc:
            raise EncryptionError(
                "Invalid PLATFORM_ENCRYPTION_KEY (must be 32 url-safe base64 bytes)"
            ) from exc

    def encrypt(self, plain: str) -> str:
        """Encrypt a plaintext string. Returns base64 ciphertext as ``str``."""
        return self._fernet.encrypt(plain.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted: str) -> str:
        """Decrypt a previously-encrypted value. Raises ``EncryptionError`` on failure."""
        try:
            plaintext = self._fernet.decrypt(encrypted.encode("utf-8"))
        except InvalidToken as exc:
            raise EncryptionError("Decryption failed: invalid or corrupted ciphertext") from exc
        return plaintext.decode("utf-8")


# Module-level singleton — the standard entrypoint.
platform_encryption = PlatformEncryption()
