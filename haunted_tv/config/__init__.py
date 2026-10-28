"""Defensive, Qt-independent configuration for the Phase A kiosk."""

from .settings import (
    AppConfig, DisplayConfig, SecurityConfig, StreamConfig,
    DEFAULT_CONFIG_PATH, load_config, save_config,
)
from .security import CredentialError, CredentialStore, hash_pin, verify_pin

__all__ = [
    "AppConfig", "DisplayConfig", "SecurityConfig", "StreamConfig",
    "DEFAULT_CONFIG_PATH", "load_config", "save_config", "CredentialError",
    "CredentialStore", "hash_pin", "verify_pin",
]
