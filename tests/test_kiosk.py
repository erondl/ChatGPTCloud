"""Offscreen UI behavior checks; these do not certify a physical Windows display."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from haunted_tv.config import AppConfig, hash_pin
from haunted_tv.streaming.pyav_capture import CaptureStatus, FramePacket, StreamState
from haunted_tv.ui.kiosk_window import KioskWindow


def await_pin(panel):
    for _ in range(200):
        if panel._pending is None:
            return
        QTest.qWait(10)
    pytest.fail("PIN check did not complete")


class Worker:
    def __init__(self):
        self.state = StreamState.DISCONNECTED
        self.packet = None
        self.reconnects = 0

    def latest_frame(self):
        return self.packet

    def status(self):
        return CaptureStatus(self.state, "test state")

    def request_reconnect(self):
        self.reconnects += 1


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def kiosk(app):
    config = AppConfig()
    config.security.admin_pin_hash = hash_pin("123456")
    worker = Worker()
    window = KioskWindow(worker, config)
    window.resize(640, 480)
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window, worker
    window._authorized_close = True
    window.close()
    app.processEvents()


def test_kiosk_has_no_visible_controls_and_esc_does_not_quit(kiosk):
    window, _ = kiosk
    assert not window.quit_panel.isVisible()
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.cursor().shape() == Qt.CursorShape.BlankCursor
    QTest.keyClick(window, Qt.Key.Key_Escape)
    window.close()
    assert window.isVisible()  # Alt+F4 / close is also blocked.


def test_f5_requests_reconnect(kiosk, app):
    window, worker = kiosk
    QTest.keyClick(window, Qt.Key.Key_F5)
    app.processEvents()
    assert worker.reconnects == 1


def test_quit_requires_pin(kiosk, app):
    window, _ = kiosk
    QTest.keyClick(window, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    app.processEvents()
    assert window.quit_panel.isVisible()
    window.quit_panel.entry.setText("000000")
    window.quit_panel.submit()
    await_pin(window.quit_panel)
    assert window.isVisible()
    window.quit_panel.entry.setText("123456")
    window.quit_panel.submit()
    await_pin(window.quit_panel)
    assert not window.isVisible()


def test_wrong_pin_attempts_are_throttled(kiosk):
    window, _ = kiosk
    panel = window.quit_panel
    panel.open()
    for _ in range(3):
        panel.entry.setText("000000")
        panel.submit()
        await_pin(panel)
    panel.entry.setText("123456")
    panel.submit()
    assert window.isVisible()
    assert "wait" in panel.label.text()


def test_live_frame_fit_and_signal_loss(kiosk):
    window, worker = kiosk
    rgb = np.zeros((90, 160, 3), dtype=np.uint8)
    rgb[:, :, 0] = 220
    worker.packet = FramePacket(1, rgb, 1.0)
    worker.state = StreamState.LIVE
    window.refresh()
    image = window.grab().toImage()
    assert image.pixelColor(320, 240).red() == 220
    assert image.pixelColor(320, 10).red() < 10  # 16:9 letterboxes within 4:3 widget.
    worker.packet = None
    worker.state = StreamState.NETWORK_ERROR
    window.refresh()
    no_signal = window.grab().toImage()
    assert no_signal.pixelColor(320, 20).red() < 60


def test_reduce_motion_freezes_static(kiosk):
    window, _ = kiosk
    window.config.display.reduce_motion = True
    a = window.grab().toImage()
    window._static_at = 0
    b = window.grab().toImage()
    assert a == b

