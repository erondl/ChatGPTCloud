"""Bounded log files with last-stage sanitization, including exception text."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import threading
from urllib.parse import quote, quote_plus

_SECRETS: set[str] = set()
_LOCK = threading.Lock()
_URL = re.compile(r"(?i)\b(?:rtsp|rtsps|https?|ftp)://[^\s<>\"']+")
_ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|token|access_token|authorization)\s*[:=]\s*[^\s,;]+")


def register_secret(value: str) -> None:
    if not value:
        return
    with _LOCK:
        _SECRETS.update({value, quote(value, safe=""), quote_plus(value, safe="")})


def redact(message: object) -> str:
    text = str(message)
    text = _URL.sub("<redacted-url>", text)
    text = _ASSIGNMENT.sub(lambda m: m.group(1) + "=<redacted>", text)
    with _LOCK:
        known = sorted(_SECRETS, key=len, reverse=True)
    for secret in known:
        text = text.replace(secret, "<redacted>")
    return text


class SanitizingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Formatting first catches exception tracebacks and %-formatted args too.
        return redact(super().format(record))


def default_log_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "HauntedTV" / "logs"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "HauntedTV" / "logs"


def setup_logging(log_dir: Path | str | None = None) -> Path:
    directory = Path(log_dir) if log_dir is not None else default_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    filename = directory / "haunted_tv.log"
    handler = RotatingFileHandler(filename, maxBytes=2 * 1024 * 1024, backupCount=4, encoding="utf-8")
    handler.setFormatter(SanitizingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    # This application owns its logging setup. Close only handlers previously installed here.
    for previous in tuple(root.handlers):
        if getattr(previous, "_haunted_tv", False):
            root.removeHandler(previous)
            previous.close()
    handler._haunted_tv = True
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("libav", "av"):
        logging.getLogger(name).disabled = True
    return filename
