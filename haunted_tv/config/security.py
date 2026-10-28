"""PIN hashing and an explicit Windows Credential Manager backend."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sys
from urllib.parse import urlsplit

PIN_PATTERN = re.compile(r"[0-9]{6,12}\Z")
HASH_PATTERN = re.compile(r"pbkdf2_sha256\$([0-9]{6,7})\$([0-9a-f]{32})\$([0-9a-f]{64})\Z")
ITERATIONS = 600_000


def hash_pin(pin: str) -> str:
    if not isinstance(pin, str) or not PIN_PATTERN.fullmatch(pin):
        raise ValueError("PIN must contain 6 to 12 digits")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def valid_pin_hash(value: object) -> bool:
    if not isinstance(value, str):
        return False
    match = HASH_PATTERN.fullmatch(value)
    return bool(match and 100_000 <= int(match.group(1)) <= 2_000_000)


def verify_pin(pin: str, stored: str) -> bool:
    if not isinstance(pin, str) or not PIN_PATTERN.fullmatch(pin) or not valid_pin_hash(stored):
        return False
    _, iterations, salt, expected = stored.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(actual, bytes.fromhex(expected))


class CredentialError(RuntimeError):
    """A generic error that never contains a backend exception or credential."""


class CredentialStore:
    SERVICE = "HauntedTV.Camera"

    @staticmethod
    def _account(url: str) -> str:
        from .settings import valid_config_url
        if not url or not valid_config_url(url):
            raise CredentialError("A password-free RTSP URL is required")
        # Include the channel so separate camera users/channels cannot overwrite one another.
        parts = urlsplit(url)
        identity = f"{parts.scheme}|{parts.hostname}|{parts.port or 554}|{parts.username or ''}|{parts.path}|{parts.query}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _backend():
        if sys.platform != "win32":
            raise CredentialError("Camera credentials require Windows Credential Manager")
        try:
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring()
        except Exception:
            raise CredentialError("Windows Credential Manager is unavailable") from None

    def get_password(self, url: str) -> str | None:
        account = self._account(url)
        try:
            value = self._backend().get_password(self.SERVICE, account)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Could not read camera credentials") from None
        if value:
            from haunted_tv.core.logging_setup import register_secret
            register_secret(value)
        return value

    def set_password(self, url: str, password: str) -> None:
        account = self._account(url)
        if not password:
            raise CredentialError("A nonempty camera password is required")
        from haunted_tv.core.logging_setup import register_secret
        register_secret(password)
        try:
            self._backend().set_password(self.SERVICE, account, password)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Could not save camera credentials") from None

    def delete_password(self, url: str) -> None:
        account = self._account(url)
        try:
            self._backend().delete_password(self.SERVICE, account)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("Could not remove camera credentials") from None
