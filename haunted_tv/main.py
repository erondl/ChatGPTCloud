"""Windowed live viewer lifecycle. Connections begin only after operator input."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from haunted_tv import __version__
from haunted_tv.config import DEFAULT_CONFIG_PATH, load_config
from haunted_tv.core.logging_setup import setup_logging


def main(argv=None):
    parser = argparse.ArgumentParser(description="Haunted TV — windowed RTSP viewer")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        setup_logging()
        config = load_config(args.config)
    except OSError:
        print("Cannot write local configuration or logs. Check folder permissions.", file=sys.stderr)
        return 2

    from PySide6.QtWidgets import QApplication
    from haunted_tv.core.session import CaptureSession
    from haunted_tv.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Haunted TV")
    app.setApplicationVersion(__version__)
    logger = logging.getLogger(__name__)
    logger.info("Starting Haunted TV %s (windowed)", __version__)
    previous_hook = sys.excepthook

    def on_exception(exc_type, exc_value, traceback):
        logger.error("Unhandled application exception", exc_info=(exc_type, exc_value, traceback))
        app.exit(1)

    sys.excepthook = on_exception
    session = CaptureSession()
    window = MainWindow(session, config, args.config)
    window.show()
    try:
        return app.exec()
    finally:
        session.stop()
        session.join(config.stream.connect_timeout_s + config.stream.read_timeout_s + 2)
        if session.is_alive():
            logger.error("Capture cleanup exceeded its configured timeout budget")
        sys.excepthook = previous_hook
        logger.info("Haunted TV stopped")
        logging.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())

