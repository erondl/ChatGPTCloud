"""Credential handling and real worker lifecycle tests without a camera."""

import threading
import time
import base64
import os
import socketserver
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import numpy as np
import pytest
import av

from haunted_tv.streaming.pyav_capture import (
    CaptureWorker,
    NoFramesError,
    StreamSettings,
    StreamState,
    classify_failure,
)
from haunted_tv.streaming.rtsp_validator import (
    InvalidRTSPURL,
    redact_sensitive,
    validate_rtsp_url,
    with_password,
)


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Worker did not reach the expected state before timeout")


@pytest.mark.parametrize("password", ["p@ss#%:word", "literal%23", "spaces and ünicode", ""])
def test_keyring_password_encoded_once(password):
    address = with_password("rtsp://viewer@127.0.0.1:8554/camera?token=abc", password)
    parts = urlsplit(address)
    assert unquote(parts.password) == password
    assert parts.hostname == "127.0.0.1"
    assert parts.query == "token=abc"
    assert validate_rtsp_url(address) == address


def test_imported_password_with_special_characters():
    address = validate_rtsp_url("rtsp://viewer:p@ss#%:word@camera.local/live")
    assert unquote(urlsplit(address).password) == "p@ss#%:word"
    assert validate_rtsp_url(address) == address


def test_unicode_path_and_encoded_slash_are_preserved_correctly():
    address = validate_rtsp_url("rtsp://camera.local/cam%2F1/porché?label=front door")
    assert address == "rtsp://camera.local/cam%2F1/porch%C3%A9?label=front%20door"
    assert validate_rtsp_url(address) == address


@pytest.mark.parametrize("address", ["", "http://camera/live", "rtsp://", "rtsp://host:0/live", "rtsp://host:65536/live", "rtsp://host/path#fragment", "rtsp://host/\nsecret"])
def test_invalid_urls_have_safe_errors(address):
    with pytest.raises(InvalidRTSPURL) as caught:
        validate_rtsp_url(address)
    if address:
        assert address not in str(caught.value)


def test_redacts_complete_url_and_query():
    redacted = redact_sensitive("failed: rtsp://user:p%40ss@host/live?token=secret (retry)")
    assert "p%40ss" not in redacted
    assert "secret" not in redacted
    assert "user" not in redacted


def test_failure_messages_never_include_exception_input():
    state, message = classify_failure(av.error.HTTPUnauthorizedError(825242872, "Unauthorized", "rtsp://user:secret@host/private"))
    assert state == StreamState.AUTHENTICATION_FAILED
    assert "secret" not in message
    assert "rtsp" not in message
    assert classify_failure(NoFramesError())[0] == StreamState.NETWORK_ERROR


def test_digits_inside_credentials_or_channel_do_not_imply_auth_failure():
    state, _ = classify_failure(TimeoutError("rtsp://viewer:401@host:403/live404 timed out"))
    assert state == StreamState.NETWORK_ERROR
    assert classify_failure(av.error.InvalidDataError(1094995529, "Invalid data"))[0] == StreamState.DECODER_ERROR


class FakeFrame:
    def __init__(self, value):
        self.value = value

    def to_ndarray(self, *, format):
        assert format == "rgb24"
        return np.full((8, 16, 3), self.value, dtype=np.uint8)


class FakePacket:
    def __init__(self, values=()):
        self.values = values

    def decode(self):
        return [FakeFrame(value) for value in self.values]


class FakeContainer:
    def __init__(self):
        self.streams = SimpleNamespace(video=[SimpleNamespace(codec_context=SimpleNamespace())])
        self.published = threading.Event()
        self.release = threading.Event()
        self.closed_by = None

    def demux(self, video):
        yield FakePacket([1, 2, 3])
        self.published.set()
        self.release.wait(2)
        yield FakePacket()

    def close(self):
        self.closed_by = threading.current_thread().ident


def test_worker_keeps_only_latest_rgb_frame_and_owns_container():
    container = FakeContainer()
    worker = CaptureWorker(StreamSettings(url="rtsp://viewer@host/live"), lambda: "p@ss#%:")
    with patch("haunted_tv.streaming.pyav_capture.av.open", return_value=container) as opened:
        worker.start()
        try:
            assert container.published.wait(2)
            packet = worker.latest_frame()
            assert packet.seq == 3
            assert np.all(packet.rgb == 3)
            assert not packet.rgb.flags.writeable
            assert worker.status().state == StreamState.LIVE
            assert unquote(urlsplit(opened.call_args.args[0]).password) == "p@ss#%:"
            assert opened.call_args.kwargs["timeout"] == (10, 8)
            assert opened.call_args.kwargs["options"]["rtsp_transport"] == "tcp"
        finally:
            worker.stop()
            container.release.set()
            worker.join(2)
    assert not worker.is_alive()
    assert container.closed_by == worker.ident
    assert worker.latest_frame() is None
    assert worker.status().state == StreamState.DISCONNECTED


def test_auth_failure_retry_limit_requires_explicit_reconnect(caplog):
    settings = StreamSettings(url="rtsp://viewer@host/live", max_auth_failures=2, reconnect_max_backoff_s=0.01)
    worker = CaptureWorker(settings)
    with patch("haunted_tv.streaming.pyav_capture.av.open", side_effect=av.error.HTTPUnauthorizedError(825242872, "Unauthorized", "rtsp://user:secret@host/live")) as opened:
        worker.start()
        try:
            wait_until(lambda: "retry limit" in worker.status().message)
            assert opened.call_count == 2
            time.sleep(0.15)
            assert opened.call_count == 2
            worker.request_reconnect()
            wait_until(lambda: opened.call_count >= 3)
        finally:
            worker.stop()
            worker.join(2)
    assert not worker.is_alive()
    assert "secret" not in caplog.text


def test_open_but_no_decoded_frames_trips_watchdog():
    container = FakeContainer()
    failed = threading.Event()

    def empty_demux(video):
        time.sleep(0.02)
        yield FakePacket()
        failed.set()

    container.demux = empty_demux
    worker = CaptureWorker(StreamSettings(url="rtsp://host/live", read_timeout_s=0.01, reconnect_max_backoff_s=1))
    with patch("haunted_tv.streaming.pyav_capture.av.open", return_value=container):
        worker.start()
        try:
            wait_until(lambda: worker.status().state == StreamState.NETWORK_ERROR)
            assert "stall" in worker.status().message
        finally:
            worker.stop()
            worker.join(2)
    assert container.closed_by == worker.ident
    assert not worker.is_alive()


def test_unconfigured_worker_sleeps_and_stops_without_opening():
    worker = CaptureWorker(StreamSettings())
    with patch("haunted_tv.streaming.pyav_capture.av.open") as opened:
        worker.start()
        wait_until(lambda: "No RTSP" in worker.status().message)
        worker.stop()
        worker.join(2)
    assert not worker.is_alive()
    opened.assert_not_called()


class AuthenticationTestServer(socketserver.ThreadingTCPServer):
    """Protocol-only fixture, never a substitute for a live camera test.

    MediaMTX v1.12.3's Basic parser rejects colons in passwords. This tiny RTSP
    receiver checks the bytes sent by the actual PyAV/FFmpeg client, then returns
    404 deliberately; it never fabricates video or claims a playable stream.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), AuthenticationTestHandler)
        self.auth_requests = 0
        self.correct_password_received = threading.Event()


class AuthenticationTestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(3)
        while True:
            first = self.rfile.readline(8192)
            if not first:
                return
            headers = {}
            for _ in range(30):
                line = self.rfile.readline(8192)
                if line in {b"\r\n", b"\n", b""}:
                    break
                key, _, value = line.partition(b":")
                headers[key.lower()] = value.strip()
            if first.startswith(b"OPTIONS "):
                code = b"200 OK"
                extra = b"Public: OPTIONS, DESCRIBE, SETUP, PLAY\r\n"
            else:
                code = b"401 Unauthorized"
                extra = b'WWW-Authenticate: Basic realm="haunted-test"\r\n'
                authorization = headers.get(b"authorization", b"")
                if authorization.startswith(b"Basic "):
                    self.server.auth_requests += 1
                    decoded = base64.b64decode(authorization[6:])
                    if decoded == b"viewer:p@ss#%:word":
                        self.server.correct_password_received.set()
                        code = b"404 Not Found"
                        extra = b""
            self.wfile.write(
                b"RTSP/1.0 " + code + b"\r\nCSeq: " + headers.get(b"cseq", b"1")
                + b"\r\n" + extra + b"Content-Length: 0\r\n\r\n"
            )
            self.wfile.flush()


@pytest.mark.skipif(not os.environ.get("HAUNTED_TV_NETWORK_TESTS"), reason="Opt-in loopback protocol tests: set HAUNTED_TV_NETWORK_TESTS=1")
@pytest.mark.parametrize("password,expected_state", [
    ("p@ss#%:word", StreamState.STREAM_UNAVAILABLE),
    ("wrong-password", StreamState.AUTHENTICATION_FAILED),
])
def test_real_ffmpeg_auth_bytes_and_failure_limit(password, expected_state):
    with AuthenticationTestServer() as server:
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        worker = CaptureWorker(StreamSettings(
            url=f"rtsp://viewer@127.0.0.1:{server.server_address[1]}/camera",
            connect_timeout_s=5, read_timeout_s=5,
            reconnect_max_backoff_s=1, max_auth_failures=3,
        ), lambda: password)
        worker.start()
        try:
            if password == "wrong-password":
                wait_until(lambda: "retry limit" in worker.status().message, timeout=12)
                assert worker.status().attempts == 3
                assert server.auth_requests == 3
                time.sleep(.2)
                assert server.auth_requests == 3
                assert not server.correct_password_received.is_set()
            else:
                wait_until(server.correct_password_received.is_set)
                wait_until(lambda: worker.status().state == expected_state)
            assert worker.status().state == expected_state
            assert worker.latest_frame() is None
        finally:
            worker.stop()
            worker.join(12)
            server.shutdown()
            serving.join(3)
            assert not worker.is_alive()

