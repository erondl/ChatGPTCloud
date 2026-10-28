import socket

import pytest

from haunted_tv.config import AppConfig
from tools import probe


class FakeConnection:
    def __init__(self, parts):
        self.parts = iter(parts)

    def recv(self, limit):
        return next(self.parts, b"")


def test_rtsp_response_reads_header_and_sdp_body():
    body = b"v=0\r\nm=video 0 RTP/AVP 96\r\n"
    code, result = probe.read_response(FakeConnection([
        b"RTSP/1.0 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n",
        body,
    ]))
    assert code == 200
    assert result == body


@pytest.mark.parametrize("reply", [
    b"HTTP/1.1 200 OK\r\n\r\n",
    b"RTSP/1.0 200 OK\r\nContent-Length: 999999999\r\n\r\n",
    b"RTSP/1.0 200 OK\r\nContent-Length: -1\r\n\r\n",
    b"RTSP/1.0 200 OK\r\nContent-Length: 4\r\n\r\nx",
])
def test_rtsp_response_rejects_malformed_or_unbounded_input(reply):
    with pytest.raises(ValueError):
        probe.read_response(FakeConnection([reply]))


def test_dns_failure_is_precise_and_does_not_try_media(monkeypatch):
    config = AppConfig()
    config.stream.url = "rtsp://private-username@camera.invalid/channel"
    monkeypatch.setattr(probe.socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror()))
    monkeypatch.setattr(probe, "media_stage", lambda _: pytest.fail("Media must not run on DNS failure"))
    stages = probe.run_probe(config)
    assert stages[-1].name == "DNS"
    assert stages[-1].outcome == "FAIL"
    assert "private-username" not in repr(stages)
    assert "camera.invalid" not in repr(stages)


def test_probe_cli_succeeds_only_on_decoded_frame(monkeypatch, capsys):
    monkeypatch.setattr(probe, "run_probe", lambda _: [probe.Stage("MEDIA", "PASS", "Decoded RGB video.")])
    assert probe.main(["--config", "/missing/config"]) == 0
    assert "MEDIA: PASS" in capsys.readouterr().out
    monkeypatch.setattr(probe, "run_probe", lambda _: [probe.Stage("TCP", "PASS", "Port open.")])
    assert probe.main(["--config", "/missing/config"]) == 1


def test_unconfigured_probe_fails_without_network():
    stages = probe.run_probe(AppConfig())
    assert stages == [probe.Stage("CONFIG", "FAIL", "No valid RTSP URL configured; run scripts/configure.bat.")]


def test_protocol_probe_strips_userinfo_and_defers_auth(monkeypatch):
    config = AppConfig()
    config.stream.url = "rtsp://operator@camera.invalid/channel"
    replies = [b"RTSP/1.0 200 OK\r\n\r\n", b"RTSP/1.0 401 Unauthorized\r\n\r\n"]
    sent = []

    class Connection(FakeConnection):
        def settimeout(self, timeout):
            pass

        def sendall(self, message):
            sent.append(message)

        def close(self):
            pass

    connection = Connection(replies)
    monkeypatch.setattr(probe.socket, "getaddrinfo", lambda *a, **k: [])
    monkeypatch.setattr(probe.socket, "create_connection", lambda *a, **k: connection)
    results = probe.protocol_stages(config)
    assert results[-1].outcome == "AUTH"
    assert b"operator" not in b"".join(sent)
    assert b"Authorization:" not in b"".join(sent)
    assert "camera.invalid" not in repr(results)
