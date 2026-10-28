"""Credential-safe RTSP diagnostics, without ping or frame persistence.

The raw protocol checks deliberately do not send authentication. PyAV handles
Basic/Digest negotiation for the final decoded-frame check. A successful frame
proves the SDP/SETUP/media path together; it does not time each protocol stage.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from dataclasses import replace
import socket
import ssl
import time
from urllib.parse import urlsplit, urlunsplit

from haunted_tv.config import CredentialStore, DEFAULT_CONFIG_PATH, load_config
from haunted_tv.streaming.pyav_capture import CaptureWorker, StreamState


@dataclass(frozen=True)
class Stage:
    name: str
    outcome: str
    detail: str


def read_response(connection) -> tuple[int, bytes]:
    """Read one bounded RTSP response; never include server text in errors."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        piece = connection.recv(4096)
        if not piece:
            raise ValueError("Incomplete RTSP response")
        data.extend(piece)
        if len(data) > 65536:
            raise ValueError("RTSP response headers exceed limit")
    header, body = bytes(data).split(b"\r\n\r\n", 1)
    lines = header.split(b"\r\n")
    first = lines[0].split(b" ", 2)
    if len(first) < 2 or first[0] != b"RTSP/1.0":
        raise ValueError("Invalid RTSP response")
    try:
        code = int(first[1])
        length = 0
        for line in lines[1:]:
            key, _, value = line.partition(b":")
            if key.strip().lower() == b"content-length":
                length = int(value.strip())
        if not 100 <= code <= 599 or not 0 <= length <= 262144:
            raise ValueError
    except ValueError:
        raise ValueError("Invalid RTSP response metadata") from None
    while len(body) < length:
        piece = connection.recv(min(4096, length - len(body)))
        if not piece:
            raise ValueError("Incomplete RTSP response body")
        body += piece
    return code, body[:length]


def request(connection, method: str, uri: str, sequence: int) -> tuple[int, bytes]:
    accept = "Accept: application/sdp\r\n" if method == "DESCRIBE" else ""
    connection.sendall(
        f"{method} {uri} RTSP/1.0\r\nCSeq: {sequence}\r\n{accept}\r\n".encode("ascii")
    )
    return read_response(connection)


def protocol_stages(config) -> list[Stage]:
    parts = urlsplit(config.stream.url)
    host, port = parts.hostname, parts.port or (322 if parts.scheme == "rtsps" else 554)
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return [Stage("DNS", "FAIL", "Host resolution failed; this does not establish camera power state.")]
    results = [Stage("DNS", "PASS", "Camera host resolved.")]
    connection = None
    current_stage = "TCP"
    try:
        connection = socket.create_connection((host, port), config.stream.connect_timeout_s)
        connection.settimeout(config.stream.read_timeout_s)
        results.append(Stage("TCP", "PASS", "Camera port accepted a connection."))
        if parts.scheme == "rtsps":
            current_stage = "TLS"
            connection = ssl.create_default_context().wrap_socket(connection, server_hostname=host)
            results.append(Stage("TLS", "PASS", "Server certificate verified."))
        # Strip userinfo. Protocol requests never print the URI or send passwords.
        authority = parts.netloc.rsplit("@", 1)[-1]
        uri = urlunsplit(parts._replace(netloc=authority))
        current_stage = "OPTIONS"
        code, _ = request(connection, "OPTIONS", uri, 1)
        if code == 200:
            results.append(Stage("OPTIONS", "PASS", "Server accepted OPTIONS."))
        else:
            results.append(Stage("OPTIONS", "INFO", f"Server returned RTSP status {code}; continuing with the media check."))
        current_stage = "DESCRIBE/SDP"
        code, body = request(connection, "DESCRIBE", uri, 2)
        if code == 200 and body.lstrip().startswith(b"v=") and b"m=video" in body:
            results.append(Stage("DESCRIBE/SDP", "PASS", "Server advertised a video session."))
        elif code in {401, 403}:
            results.append(Stage("DESCRIBE/SDP", "AUTH", "Authentication required; PyAV will negotiate in the media check."))
        else:
            results.append(Stage("DESCRIBE/SDP", "INFO", f"RTSP status {code}; video SDP not verified by the unauthenticated probe."))
    except (OSError, ValueError, UnicodeError):
        results.append(Stage(current_stage, "FAIL", "Direct stage failed; the independent PyAV media check follows."))
    finally:
        if connection is not None:
            connection.close()
    return results


def media_stage(config) -> Stage:
    settings = replace(config.stream, max_auth_failures=1)
    store = CredentialStore()
    # Password-free sources remain testable on Linux without a keyring backend.
    provider = (lambda: store.get_password(settings.url)) if urlsplit(settings.url).username else None
    worker = CaptureWorker(settings, password_provider=provider)
    worker.start()
    deadline = time.monotonic() + settings.connect_timeout_s + settings.read_timeout_s + 3
    result = Stage("MEDIA", "FAIL", "No decoded frame before the probe deadline.")
    try:
        while time.monotonic() < deadline:
            packet = worker.latest_frame()
            if packet is not None:
                height, width = packet.rgb.shape[:2]
                result = Stage("MEDIA", "PASS", f"Decoded RGB video {width}x{height}; authenticated SDP, SETUP and media delivery succeeded together.")
                break
            status = worker.status()
            if status.state in {
                StreamState.AUTHENTICATION_FAILED, StreamState.STREAM_UNAVAILABLE,
                StreamState.NETWORK_ERROR, StreamState.DECODER_ERROR,
            }:
                # Capture status messages are fixed strings, not FFmpeg exception text.
                result = Stage("MEDIA", "FAIL", status.message)
                break
            time.sleep(.05)
    finally:
        worker.stop()
        worker.join(settings.connect_timeout_s + settings.read_timeout_s + 2)
        if worker.is_alive():
            result = Stage("MEDIA", "FAIL", "Capture did not finish within its configured shutdown deadline.")
    return result


def run_probe(config) -> list[Stage]:
    if not config.stream.url:
        return [Stage("CONFIG", "FAIL", "No valid RTSP URL configured; run scripts/configure.bat.")]
    results = protocol_stages(config)
    if results[-1].name == "DNS" and results[-1].outcome == "FAIL":
        return results
    results.append(media_stage(config))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe the configured camera without recording or printing credentials.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args(argv)
    config = load_config(args.config, create=False)
    try:
        results = run_probe(config)
    except Exception:
        # Includes keyring/platform failures. Neither raw URL nor backend text is printed.
        results = [Stage("PROBE", "FAIL", "Probe failed; check configuration, credentials and platform dependencies.")]
    for stage in results:
        print(f"{stage.name}: {stage.outcome} — {stage.detail}")
    return 0 if results[-1].name == "MEDIA" and results[-1].outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
