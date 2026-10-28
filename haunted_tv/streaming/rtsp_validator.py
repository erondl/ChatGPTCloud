"""RTSP URL handling without exposing credentials in error messages."""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit


class InvalidRTSPURL(ValueError):
    """An invalid RTSP URL. Messages intentionally contain no input values."""


def validate_rtsp_url(url: str) -> str:
    """Validate and canonicalize a URL, preserving already escaped credentials.

    Literal ``@ # % :`` characters in an embedded password are accepted. The
    final @ before the host separates userinfo, so a literal @ in a password is
    encoded rather than mistaken for the host. Configuration must store the
    password separately; support here is for import/probe operations only.
    """
    if not isinstance(url, str) or not url or url != url.strip():
        raise InvalidRTSPURL("Enter an RTSP URL without surrounding whitespace.")
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise InvalidRTSPURL("Control characters are not allowed in an RTSP URL.")
    scheme, sep, remainder = url.partition("://")
    if not sep or scheme.lower() != "rtsp":
        raise InvalidRTSPURL("Phase A supports rtsp:// URLs only.")
    authority, slash, path = remainder.partition("/")
    userinfo, at, host = authority.rpartition("@")
    if at:
        username, colon, password = userinfo.partition(":")
        if not username:
            raise InvalidRTSPURL("A stream username must not be empty.")
        credentials = quote(unquote(username), safe="")
        if colon:
            credentials += ":" + quote(unquote(password), safe="")
        authority = credentials + "@" + host
    try:
        parts = urlsplit(scheme.lower() + "://" + authority + slash + path)
        if not parts.hostname or any(c.isspace() for c in parts.hostname):
            raise ValueError
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError
        if parts.fragment:
            raise ValueError
    except ValueError:
        raise InvalidRTSPURL("The stream host, port, or path is invalid.") from None
    return urlunsplit(parts._replace(
        path=quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
        query=quote(parts.query, safe="/%?:@!$&'()*+,;=-._~"),
    ))


def with_password(url: str, password: str | None) -> str:
    """Insert a raw keyring password exactly once; never use this value in logs."""
    validated = validate_rtsp_url(url)
    if password is None:
        return validated
    parts = urlsplit(validated)
    if parts.username is None:
        if password:
            raise InvalidRTSPURL("A username is required when using a password.")
        return validated
    host = parts.netloc.rsplit("@", 1)[-1]
    user = quote(unquote(parts.username), safe="")
    return urlunsplit(parts._replace(netloc=f"{user}:{quote(password, safe='')}@{host}"))


def redact_sensitive(text: str) -> str:
    """Remove complete RTSP URLs, including path/query tokens, from text."""
    return re.sub(r"rtsps?://[^\s\"'<>]+", "[RTSP URL redacted]", str(text), flags=re.I)

