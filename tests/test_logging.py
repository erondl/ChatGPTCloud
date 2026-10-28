import logging
from logging.handlers import RotatingFileHandler

from haunted_tv.core.logging_setup import (
    SanitizingFormatter, redact, register_secret, setup_logging,
)


def test_redacts_urls_and_queries():
    text = redact("Opening rtsp://user:p%40ss@camera/live?token=sensitive failed")
    assert text == "Opening <redacted-url> failed"
    assert "sensitive" not in redact("https://camera/path?token=sensitive")


def test_redacts_secret_in_raw_and_encoded_forms():
    register_secret("Strange @#%:password")
    text = redact("Strange @#%:password and Strange%20%40%23%25%3Apassword")
    assert "Strange" not in text


def test_formatter_redacts_tracebacks_and_args():
    register_secret("TracebackSecretXYZ")
    formatter = SanitizingFormatter("%(message)s")
    try:
        raise ValueError("TracebackSecretXYZ from rtsp://u:p@camera/live")
    except ValueError:
        import sys
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "failed %s", ("TracebackSecretXYZ",), sys.exc_info())
    formatted = formatter.format(record)
    assert "TracebackSecretXYZ" not in formatted
    assert "camera/live" not in formatted
    assert "ValueError" in formatted


def test_rotating_log_is_bounded_and_reinitialization_closes_previous(tmp_path):
    root = logging.getLogger()
    before = tuple(root.handlers)
    previous_level = root.level
    try:
        filename = setup_logging(tmp_path)
        logging.getLogger("haunted_tv.tests").info("Connect rtsp://user:password@camera/live")
        handlers = [h for h in root.handlers if getattr(h, "_haunted_tv", False)]
        assert len(handlers) == 1
        first = handlers[0]
        assert isinstance(first, RotatingFileHandler)
        assert first.backupCount == 4  # Active file + four backups = five files.
        assert first.maxBytes == 2 * 1024 * 1024
        first.flush()
        contents = filename.read_text()
        assert "user:password" not in contents
        assert "<redacted-url>" in contents
        setup_logging(tmp_path)
        assert first.stream is None
        assert len([h for h in root.handlers if getattr(h, "_haunted_tv", False)]) == 1
    finally:
        for handler in tuple(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(previous_level)
