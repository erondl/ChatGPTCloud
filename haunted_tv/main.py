"""Phase A application lifecycle. No synthetic video or automatic network calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import logging
from pathlib import Path
import sys
from urllib.parse import urlsplit

from haunted_tv import __version__
from haunted_tv.config import DEFAULT_CONFIG_PATH, CredentialStore, load_config
from haunted_tv.config.security import valid_pin_hash
from haunted_tv.core.logging_setup import setup_logging
from haunted_tv.core.power import SleepGuard


def main(argv=None):
    parser = argparse.ArgumentParser(description="Haunted TV — Phase A live RTSP kiosk")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        logfile = setup_logging()
        config = load_config(args.config)
    except OSError:
        print("Cannot write local configuration or log directory. Check folder permissions.", file=sys.stderr)
        return 2
    if not valid_pin_hash(config.security.admin_pin_hash):
        print("Set an operator PIN before entering kiosk mode. Run scripts\\configure.bat on Windows",
              "or python -m haunted_tv.config.setup --config <path>.", file=sys.stderr)
        return 2

    from PySide6.QtWidgets import QApplication
    from haunted_tv.streaming.pyav_capture import CaptureWorker, StreamSettings
    from haunted_tv.ui.kiosk_window import KioskWindow

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Haunted TV")
    app.setApplicationVersion(__version__)
    logger = logging.getLogger(__name__)
    logger.info("Starting Haunted TV %s (Phase A)", __version__)

    def on_exception(exc_type, exc_value, traceback):
        logger.error("Unhandled application exception", exc_info=(exc_type, exc_value, traceback))
        app.exit(1)

    sys.excepthook = on_exception
    store = CredentialStore()
    # No keyring interaction for an unconfigured or anonymous RTSP source.
    provider = (lambda: store.get_password(config.stream.url)) if urlsplit(config.stream.url).username else None
    capture = CaptureWorker(StreamSettings(**asdict(config.stream)), password_provider=provider)
    guard = SleepGuard()
    window = KioskWindow(capture, config)
    capture.start()
    guard.start()
    window.open_on_monitor()
    try:
        return app.exec()
    finally:
        capture.stop()
        guard.stop()
        # Both joins happen after the event loop exits. Containers never cross threads.
        capture.join(config.stream.connect_timeout_s + config.stream.read_timeout_s + 2)
        guard.join(2)
        if capture.is_alive():
            logger.error("Capture did not stop within its configured timeout budget")
        logger.info("Haunted TV stopped")
        logging.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
