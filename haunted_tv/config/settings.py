"""TOML is configuration, never a password store."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import parse_qsl, urlsplit

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib


LOG = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "haunted_tv.toml"


@dataclass
class StreamConfig:
    url: str = ""
    transport: str = "tcp"
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 8.0
    reconnect_max_backoff_s: float = 30.0
    max_auth_failures: int = 3


@dataclass
class DisplayConfig:
    monitor: int = 0
    fps_cap: int = 60
    reduce_motion: bool = False


@dataclass
class SecurityConfig:
    admin_pin_hash: str = ""


@dataclass
class AppConfig:
    stream: StreamConfig = field(default_factory=StreamConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def valid_config_url(value: object) -> bool:
    """Allow an unconfigured stream, but never persist URL passwords or tokens."""
    if not isinstance(value, str):
        return False
    if value == "":
        return True
    if any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parts = urlsplit(value)
        if parts.scheme != "rtsp" or not parts.hostname:
            return False
        if parts.password is not None or parts.fragment:
            return False
        if parts.port is not None and not (1 <= parts.port <= 65535):
            return False
        sensitive_keys = {"password", "passwd", "pass", "pwd", "token", "access_token", "api_key"}
        if any(k.casefold() in sensitive_keys for k, _ in parse_qsl(parts.query)):
            return False
        return True
    except (TypeError, ValueError):
        return False


def _table(data: dict, name: str) -> dict:
    candidate = data.get(name, {})
    if not isinstance(candidate, dict):
        LOG.warning("Invalid configuration section %s; using defaults", name)
        return {}
    return candidate


def _number(table: dict, key: str, default: float | int, low: float, high: float, *, integer=False):
    value = table.get(key, default)
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or not low <= value <= high or not math.isfinite(value):
        LOG.warning("Invalid configuration value for %s; using default", key)
        return default
    return value


def _validated(data: dict) -> AppConfig:
    cfg = AppConfig()
    stream, display, security = (_table(data, x) for x in ("stream", "display", "security"))
    url = stream.get("url", "")
    if valid_config_url(url):
        cfg.stream.url = url
    else:
        LOG.warning("Invalid or credential-bearing stream URL; stream left unconfigured")
    transport = stream.get("transport", "tcp")
    if isinstance(transport, str) and transport in {"tcp", "udp"}:
        cfg.stream.transport = transport
    else:
        LOG.warning("Invalid stream transport; using TCP")
    cfg.stream.connect_timeout_s = _number(stream, "connect_timeout_s", 10.0, 0.1, 120.0)
    cfg.stream.read_timeout_s = _number(stream, "read_timeout_s", 8.0, 0.1, 120.0)
    cfg.stream.reconnect_max_backoff_s = _number(stream, "reconnect_max_backoff_s", 30.0, 1.0, 300.0)
    cfg.stream.max_auth_failures = _number(stream, "max_auth_failures", 3, 1, 3, integer=True)
    cfg.display.monitor = _number(display, "monitor", 0, 0, 63, integer=True)
    cfg.display.fps_cap = _number(display, "fps_cap", 60, 1, 120, integer=True)
    reduce_motion = display.get("reduce_motion", False)
    if type(reduce_motion) is bool:
        cfg.display.reduce_motion = reduce_motion
    else:
        LOG.warning("Invalid reduce_motion value; using default")
    pin_hash = security.get("admin_pin_hash", "")
    from .security import valid_pin_hash
    if pin_hash == "" or valid_pin_hash(pin_hash):
        cfg.security.admin_pin_hash = pin_hash
    else:
        LOG.warning("Invalid admin PIN hash; PIN must be configured again")
    return cfg


def load_config(path: Path | str = DEFAULT_CONFIG_PATH, *, create: bool = True) -> AppConfig:
    """Bad input falls back without logging source text or parser exceptions."""
    path = Path(path)
    if not path.exists():
        cfg = AppConfig()
        if create:
            save_config(cfg, path)
        return cfg
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError, UnicodeError):
        LOG.warning("Configuration could not be read; using safe defaults")
        return AppConfig()
    return _validated(data)


def save_config(config: AppConfig, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    """Atomically save only validated values, refusing accidental secret storage."""
    if not valid_config_url(config.stream.url):
        raise ValueError("Stream URL must be valid RTSP and must not contain a password or token")
    # Validate before serialization, including dataclasses changed directly by a caller.
    from dataclasses import asdict
    cfg = _validated(asdict(config))
    # TOML permits Unicode directly, but does not permit JSON's surrogate-pair
    # escapes for non-BMP characters (for example an emoji in a stream path).
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    contents = (
        "# Haunted TV — Phase A. Store the camera password in Windows Credential Manager.\n"
        "[stream]\n"
        f"url = {quote(cfg.stream.url)}\n"
        f"transport = {quote(cfg.stream.transport)}\n"
        f"connect_timeout_s = {cfg.stream.connect_timeout_s}\n"
        f"read_timeout_s = {cfg.stream.read_timeout_s}\n"
        f"reconnect_max_backoff_s = {cfg.stream.reconnect_max_backoff_s}\n"
        f"max_auth_failures = {cfg.stream.max_auth_failures}\n\n"
        "[display]\n"
        f"monitor = {cfg.display.monitor}\n"
        f"fps_cap = {cfg.display.fps_cap}\n"
        f"reduce_motion = {str(cfg.display.reduce_motion).lower()}\n\n"
        "[security]\n"
        f"admin_pin_hash = {quote(cfg.security.admin_pin_hash)}\n"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".haunted_tv_", delete=False) as target:
            temp_name = target.name
            target.write(contents)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
