from dataclasses import asdict
from pathlib import Path
import sys

import pytest

from haunted_tv.config import (
    AppConfig, CredentialError, CredentialStore, hash_pin, load_config, save_config, verify_pin,
)
from haunted_tv.config.settings import valid_config_url


def test_first_run_creates_defaults_and_roundtrips(tmp_path):
    path = tmp_path / "config" / "haunted_tv.toml"
    cfg = load_config(path)
    assert cfg.stream.url == ""
    assert cfg.stream.transport == "tcp"
    assert path.exists()
    assert asdict(load_config(path)) == asdict(cfg)


def test_valid_custom_config_roundtrip(tmp_path):
    cfg = AppConfig()
    cfg.stream.url = "rtsp://visitor%40home@127.0.0.1:8554/camera?mode=low"
    cfg.stream.transport = "udp"
    cfg.display.monitor = 1
    cfg.display.fps_cap = 25
    cfg.display.reduce_motion = True
    cfg.security.admin_pin_hash = hash_pin("112233")
    path = tmp_path / "settings.toml"
    save_config(cfg, path)
    assert asdict(load_config(path)) == asdict(cfg)
    assert "112233" not in path.read_text()


def test_non_bmp_unicode_url_roundtrips(tmp_path):
    cfg = AppConfig()
    cfg.stream.url = "rtsp://camera.local/porch/🎃?label=入口"
    path = tmp_path / "unicode.toml"
    save_config(cfg, path)
    assert load_config(path).stream.url == cfg.stream.url
    assert "🎃" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("raw", [
    "[stream", "url = 'unterminated", "[stream]\nurl = 12",
    "stream = true\ndisplay = 'bad'\nsecurity = []",
])
def test_malformed_config_falls_back_without_crash(tmp_path, raw):
    path = tmp_path / "bad.toml"
    path.write_text(raw)
    cfg = load_config(path)
    assert cfg.stream.url == ""
    assert cfg.display.monitor == 0


@pytest.mark.parametrize("url", [
    "rtsp://visitor:secret@camera/live",
    "rtsp://visitor:s%40%23%25%3A@camera/live",
    "rtsp://camera/live?password=secret", "rtsp://camera/live?TOKEN=secret",
    "http://camera/live", "rtsp://camera:0/live", "rtsp://camera:65536/live",
    "rtsp://camera:bad/live", "rtsp://[broken/live", "rtsp://camera/a b", "rtsp://camera/live#secret",
])
def test_rejects_invalid_or_credentialed_urls(tmp_path, url):
    assert not valid_config_url(url)
    cfg = AppConfig()
    cfg.stream.url = url
    with pytest.raises(ValueError, match="must not contain"):
        save_config(cfg, tmp_path / "bad.toml")


def test_password_in_file_is_not_used_or_logged(tmp_path, caplog):
    path = tmp_path / "secret.toml"
    path.write_text('[stream]\nurl = "rtsp://user:HighlySecretPassword@camera/live"')
    cfg = load_config(path)
    assert cfg.stream.url == ""
    assert "HighlySecretPassword" not in caplog.text
    assert "camera/live" not in caplog.text


def test_bad_types_ranges_and_nonfinite_values(tmp_path):
    path = tmp_path / "types.toml"
    path.write_text("""[stream]
url = false
transport = []
connect_timeout_s = nan
read_timeout_s = inf
reconnect_max_backoff_s = -10
max_auth_failures = true
[display]
monitor = -1
fps_cap = "60"
reduce_motion = "false"
[security]
admin_pin_hash = []
""")
    assert asdict(load_config(path)) == asdict(AppConfig())


def test_enormous_integer_falls_back(tmp_path):
    path = tmp_path / "huge.toml"
    path.write_text("[display]\nmonitor = " + "9" * 2000)
    assert load_config(path).display.monitor == 0


def test_pin_hash_is_salted_and_verifies():
    first = hash_pin("123456")
    second = hash_pin("123456")
    assert first != second
    assert "123456" not in first
    assert verify_pin("123456", first)
    assert not verify_pin("123457", first)
    assert not verify_pin("123456", "")
    assert not verify_pin("123456", "pbkdf2_sha256$99999999$" + "0" * 32 + "$" + "0" * 64)
    assert not verify_pin("123456", None)


@pytest.mark.parametrize("pin", ["", "12345", "1234567890123", "abcdef", "１２３４５６"])
def test_pin_format(pin):
    with pytest.raises(ValueError):
        hash_pin(pin)


def test_credential_store_never_falls_back_to_other_backends(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    store = CredentialStore()
    with pytest.raises(CredentialError, match="Windows Credential Manager"):
        store.set_password("rtsp://user@camera/live", "secret")
    with pytest.raises(CredentialError, match="Windows Credential Manager"):
        store.get_password("rtsp://user@camera/live")


def test_credential_keys_are_stable_and_do_not_contain_url():
    key = CredentialStore._account("rtsp://user@camera:554/live")
    assert key == CredentialStore._account("rtsp://user@camera/live")
    assert key != CredentialStore._account("rtsp://other@camera/live")
    assert key != CredentialStore._account("rtsp://user@camera/other")
    assert "camera" not in key


def test_credential_backend_errors_do_not_leak(monkeypatch):
    class BrokenBackend:
        def get_password(self, *args):
            raise RuntimeError("password=secret")

    monkeypatch.setattr(CredentialStore, "_backend", staticmethod(lambda: BrokenBackend()))
    with pytest.raises(CredentialError) as exc:
        CredentialStore().get_password("rtsp://user@camera/live")
    assert "secret" not in str(exc.value)
    assert exc.value.__suppress_context__
