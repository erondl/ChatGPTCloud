"""Phase A clean display; CRT, bezels and the admin console belong to later phases."""
from __future__ import annotations

import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from haunted_tv.config import verify_pin


class _PinSignals(QObject):
    result = Signal(bool)


class _PinCheck(QRunnable):
    def __init__(self, pin, pin_hash):
        super().__init__()
        self.pin = pin
        self.pin_hash = pin_hash
        self.signals = _PinSignals()

    def run(self):
        accepted = verify_pin(self.pin, self.pin_hash)
        self.pin = ""
        self.signals.result.emit(accepted)


class QuitPanel(QWidget):
    """Hidden PIN entry inside the kiosk, never a separate modal dialog."""
    def __init__(self, pin_hash, on_authorized, parent):
        super().__init__(parent)
        self.pin_hash = pin_hash
        self.on_authorized = on_authorized
        self.failures = 0
        self.locked_until = 0.0
        self._pending = None
        self.setFixedSize(340, 150)
        self.setStyleSheet(
            "QuitPanel { background: #151b18; border: 1px solid #607b66; }"
            "QLabel { color: #c1d4c6; }"
            "QLineEdit { color: #d9e4dc; background: #080c09; padding: 8px; }"
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Enter operator PIN to exit", self)
        self.entry = QLineEdit(self)
        self.entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry.setMaxLength(12)
        self.entry.returnPressed.connect(self.submit)
        layout.addWidget(self.label)
        layout.addWidget(self.entry)
        layout.addWidget(QLabel("Enter to confirm · Esc to cancel", self))
        self.hide()

    def open(self):
        self.label.setText("Enter operator PIN to exit")
        self.entry.clear()
        self.show()
        self.raise_()
        self.entry.setFocus()

    def submit(self):
        if self._pending is not None:
            return
        if time.monotonic() < self.locked_until:
            self.label.setText("Please wait before trying again")
            self.entry.clear()
            return
        pin = self.entry.text()
        self.entry.clear()
        self.label.setText("Checking PIN…")
        self._pending = _PinCheck(pin, self.pin_hash)
        self._pending.signals.result.connect(self._checked)
        QThreadPool.globalInstance().start(self._pending)

    def _checked(self, accepted):
        self._pending = None
        if accepted:
            self.on_authorized()
            return
        self.failures += 1
        if self.failures >= 3:
            self.locked_until = time.monotonic() + 30
            self.failures = 0
        self.label.setText("PIN not accepted")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.parentWidget().setFocus()
        else:
            super().keyPressEvent(event)


class KioskWindow(QWidget):
    def __init__(self, worker, config):
        super().__init__()
        self.worker = worker
        self.config = config
        self._authorized_close = False
        self._sequence = -1
        self._image = None
        self._rng = np.random.default_rng()
        self._static_image = None
        self._static_at = 0.0
        self.setWindowTitle("Haunted TV")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.quit_panel = QuitPanel(config.security.admin_pin_hash, self._quit, self)
        self.quit_panel.setCursor(Qt.CursorShape.ArrowCursor)
        self._shortcuts = []
        for sequence, callback in (("F5", worker.request_reconnect), ("Ctrl+Alt+Q", self.quit_panel.open)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(max(1, round(1000 / config.display.fps_cap)))

    def open_on_monitor(self):
        screens = QApplication.screens()
        screen = screens[min(self.config.display.monitor, len(screens) - 1)]
        self.setGeometry(screen.geometry())
        self.winId()
        self.windowHandle().setScreen(screen)
        self.showFullScreen()

    def refresh(self):
        packet = self.worker.latest_frame()
        if packet is not None and packet.seq != self._sequence:
            # Own the QImage data so the latest-frame slot can be overwritten safely.
            rgb = np.ascontiguousarray(packet.rgb)
            h, w, _ = rgb.shape
            self._image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
            self._sequence = packet.seq
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#050706"))
        state = self.worker.status().state.value
        if state == "live" and self._image is not None:
            iw, ih = self._image.width(), self._image.height()
            scale = min(self.width() / iw, self.height() / ih)
            rect = QRectF((self.width() - iw * scale) / 2, (self.height() - ih * scale) / 2,
                          iw * scale, ih * scale)
            painter.drawImage(rect, self._image)
        else:
            self._paint_signal(painter, state)

    def _paint_signal(self, painter, state):
        now = time.monotonic()
        error = state in {"authentication_failed", "stream_unavailable", "decoder_error"}
        if error:
            colors = ("#808080", "#808000", "#008080", "#008000", "#800080", "#800000", "#000080")
            for index, color in enumerate(colors):
                painter.fillRect(QRectF(index * self.width() / 7, 0, self.width() / 7 + 1, self.height()), QColor(color))
        else:
            # Narrow, constant luminance distribution: no full-screen strobe.
            # reduce_motion freezes static as well as future animated effects.
            if self._static_image is None or (not self.config.display.reduce_motion and now - self._static_at >= 0.1):
                gray = self._rng.integers(20, 55, (90, 160), dtype=np.uint8)
                self._static_image = QImage(gray.data, 160, 90, 160, QImage.Format.Format_Grayscale8).copy()
                self._static_at = now
            painter.drawImage(self.rect(), self._static_image)
        label = "CHANNEL ERROR" if error else "NO SIGNAL"
        font = QFont("Consolas", max(12, round(self.height() / 22)))
        font.setBold(True)
        painter.setFont(font)
        backdrop = QRectF(0, self.height() * .4, self.width(), self.height() * .2)
        painter.fillRect(backdrop, QColor(0, 0, 0, 180))
        painter.setPen(QColor("#d8e4d6"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, label)

    def resizeEvent(self, event):
        self.quit_panel.move((self.width() - self.quit_panel.width()) // 2,
                             (self.height() - self.quit_panel.height()) // 2)
        super().resizeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.quit_panel.hide()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Includes Alt+F4/window-manager close. Windows shutdown still terminates apps.
        if self._authorized_close:
            self._timer.stop()
            event.accept()
        else:
            event.ignore()

    def _quit(self):
        self._authorized_close = True
        self.close()

