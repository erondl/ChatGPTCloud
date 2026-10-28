from urllib.parse import urlsplit

import pytest

from haunted_tv.config import AppConfig, load_config, save_config
from haunted_tv.config.connection import ConnectionInput, parse_connection_input
from haunted_tv.streaming.rtsp_validator import with_password


def test_password_free_url_uses_stored_credential():
    result = parse_connection_input("rtsp://viewer@camera.local:554/live")
    assert result.url == "rtsp://viewer@camera.local:554/live"
    assert result.password is None


def test_anonymous_connection_is_supported():
    result = parse_connection_input("rtsp://camera.local/live")
    assert result == ConnectionInput("rtsp://camera.local/live")
    assert result.password is None


def test_encoded_embedded_password_is_decoded_exactly_once():
    result = parse_connection_input("rtsp://viewer:p%40%23%25%3A%2540@camera.local/live")
    assert result.url == "rtsp://viewer@camera.local/live"
    assert result.password == "p@#%:%40"
    assert with_password(result.url, result.password) == "rtsp://viewer:p%40%23%25%3A%2540@camera.local/live"


def test_raw_special_embedded_password():
    result = parse_connection_input("rtsp://viewer:p@#%:@camera.local/live")
    assert result.url == "rtsp://viewer@camera.local/live"
    assert result.password == "p@#%:"


def test_nonempty_separate_fields_override_embedded_values_verbatim():
    result = parse_connection_input(
        "rtsp://embedded:old-secret@camera.local/live", "new%40@user", "new%40@#%:secret",
    )
    assert result.url == "rtsp://new%2540%40user@camera.local/live"
    assert result.password == "new%40@#%:secret"
    assert urlsplit(with_password(result.url, result.password)).password == "new%2540%40%23%25%3Asecret"


def test_username_only_override_keeps_embedded_password():
    result = parse_connection_input("rtsp://old:embedded@camera.local/live", "new")
    assert result.url == "rtsp://new@camera.local/live"
    assert result.password == "embedded"


def test_password_only_override_keeps_embedded_username():
    result = parse_connection_input("rtsp://name%40home:old@camera.local/live", password="new")
    assert result.url == "rtsp://name%40home@camera.local/live"
    assert result.password == "new"


def test_empty_separate_password_keeps_explicit_empty_embedded_password():
    result = parse_connection_input("rtsp://viewer:@camera.local/live")
    assert result.url == "rtsp://viewer@camera.local/live"
    assert result.password == ""


def test_ipv6_path_and_query_encoding_are_preserved():
    result = parse_connection_input("rtsp://viewer:p%2540@[2001:db8::1]:8554/camera%20one?mode=low&label=a%2Fb")
    assert result.url == "rtsp://viewer@[2001:db8::1]:8554/camera%20one?mode=low&label=a%2Fb"
    assert result.password == "p%40"


def test_unicode_path_is_canonicalized_without_changing_existing_escapes():
    result = parse_connection_input("rtsp://camera.local/🎃/entrance%20one?label=入口")
    assert result.url == "rtsp://camera.local/%F0%9F%8E%83/entrance%20one?label=%E5%85%A5%E5%8F%A3"


def test_result_repr_never_contains_password():
    result = parse_connection_input("rtsp://viewer:PrivatePasswordValue@camera.local/live")
    assert "PrivatePasswordValue" not in repr(result)
    assert "password=" not in repr(result)


def test_result_url_can_be_saved_without_password(tmp_path):
    result = parse_connection_input("rtsp://viewer:NeverWriteThis@camera.local/live")
    cfg = AppConfig()
    cfg.stream.url = result.url
    path = tmp_path / "connection.toml"
    save_config(cfg, path)
    assert load_config(path).stream.url == result.url
    assert "NeverWriteThis" not in path.read_text()


@pytest.mark.parametrize("url,username,password", [
    ("rtsp://viewer:SecretValue@camera.local/live?token=SecretValue", "", ""),
    ("rtsp://camera.local/live?Password=SecretValue", "", ""),
    ("http://viewer:SecretValue@camera.local/live", "", ""),
    ("rtsp://viewer:SecretValue@camera.local:wrong/live", "", ""),
    ("rtsp://viewer:SecretValue@camera.local:0/live", "", ""),
    ("rtsp://camera.local/live", "", "SecretValue"),
    ("rtsp://camera.local/live", "bad\nusername", "SecretValue"),
    ("rtsp://camera.local/live", "viewer", "SecretValue\x00"),
    (None, "viewer", "SecretValue"),
])
def test_errors_do_not_contain_credentials_or_input(url, username, password):
    with pytest.raises(ValueError) as exc:
        parse_connection_input(url, username, password)
    assert "SecretValue" not in str(exc.value)
    assert "camera.local" not in str(exc.value)
