"""Windows execution state belongs to the calling thread; restore on that thread."""
from __future__ import annotations

import ctypes
import logging
import sys
import threading

logger = logging.getLogger(__name__)


class SleepGuard(threading.Thread):
    def __init__(self):
        super().__init__(name="sleep-guard", daemon=True)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        if sys.platform != "win32":
            return
        set_state = ctypes.windll.kernel32.SetThreadExecutionState
        try:
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED.
            if not set_state(0x80000003):
                logger.warning("Windows sleep prevention was not granted")
            self._stop_event.wait()
        finally:
            set_state(0x80000000)

