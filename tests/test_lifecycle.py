"""Lifecycle smoke and Windows API contract, not a substitute for Windows hardware."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from haunted_tv.config import AppConfig, hash_pin, save_config
from haunted_tv.core import power
from haunted_tv.ui.kiosk_window import KioskWindow


def test_sleep_guard_restores_calling_thread_execution_state(monkeypatch):
    calls = []
    def set_state(flags):
        calls.append(flags)
        return 1
    monkeypatch.setattr(power.sys, "platform", "win32")
    monkeypatch.setattr(power.ctypes, "windll", SimpleNamespace(
        kernel32=SimpleNamespace(SetThreadExecutionState=set_state)), raising=False)
    guard = power.SleepGuard()
    guard.stop()
    guard.run()
    assert calls == [0x80000003, 0x80000000]


def test_main_no_signal_lifecycle_exits_and_cleans_workers(monkeypatch, tmp_path):
    from haunted_tv.main import main
    import threading

    config = AppConfig()
    config.security.admin_pin_hash = hash_pin("123456")
    path = tmp_path / "haunted_tv.toml"
    save_config(config, path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    original = KioskWindow.open_on_monitor
    def open_and_exit(window):
        original(window)
        assert window.isFullScreen()
        assert not window.quit_panel.isVisible()
        QTimer.singleShot(100, window._quit)
    monkeypatch.setattr(KioskWindow, "open_on_monitor", open_and_exit)
    # Keep the app alive in this scope for both first and reused Qt instances.
    app = QApplication.instance() or QApplication([])
    assert main(["--config", str(path)]) == 0
    assert not [t for t in threading.enumerate() if t.name in {"rtsp-capture", "sleep-guard"}]
    assert "Haunted TV stopped" in (tmp_path / "HauntedTV/logs/haunted_tv.log").read_text()
