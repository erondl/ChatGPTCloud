"""Qt-independent parsing for the window's connection fields.

The URL returned here is safe to persist in TOML. The password remains a separate
in-memory value for the capture worker or Windows Credential Manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from haunted_tv.streaming.rtsp_validator import InvalidRTSPURL, validate_rtsp_url

from .settings import valid_config_url


@dataclass(frozen=True)
class ConnectionInput:
    url: str
    password: str | None = field(default=None, repr=False)


def parse_connection_input(url: str, username: str = "", password: str = "") -> ConnectionInput:
    """Separate credentials without double-decoding literal percent sequences.

    Nonempty separate fields override their corresponding embedded values. An
    absent password is ``None`` so callers can reuse the stored vault credential.
    An explicitly empty embedded password is preserved as an empty string.
    """
    if not all(isinstance(value, str) for value in (url, username, password)):
        raise ValueError("Connection fields must contain text.")
    if any(ord(char) < 32 or ord(char) == 127 for char in username + password):
        raise ValueError("Control characters are not allowed in credentials.")
    try:
        normalized = validate_rtsp_url(url)
        parts = urlsplit(normalized)
        embedded_password = unquote(parts.password) if parts.password is not None else None
        selected_password = password if password else embedded_password
        selected_username = quote(username, safe="") if username else parts.username
        host_authority = parts.netloc.rsplit("@", 1)[-1]
        authority = f"{selected_username}@{host_authority}" if selected_username else host_authority
        safe_url = urlunsplit(parts._replace(netloc=authority))
        if selected_password and not selected_username:
            raise ValueError
        if not valid_config_url(safe_url):
            raise ValueError
    except (InvalidRTSPURL, ValueError):
        # Never expose parser exceptions that may contain the original URL.
        raise ValueError("Enter a valid RTSP URL without credential query parameters.") from None
    return ConnectionInput(url=safe_url, password=selected_password)
