"""Video surface only; never takes control of other application windows."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QWidget


class VideoWidget(QWidget):
    def __init__(self, worker, config, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.config = config
        self._sequence = -1
        self._image = None
        self.setMinimumSize(320, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(max(1, round(1000 / config.display.fps_cap)))

    def refresh(self):
        packet = self.worker.latest_frame()
        if packet is None:
            self._sequence = -1
            self._image = None
        elif packet.seq != self._sequence:
            rgb = np.ascontiguousarray(packet.rgb)
            height, width, _ = rgb.shape
            self._image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
            self._sequence = packet.seq
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#090d12"))
        status = self.worker.status()
        if status.state.value == "live" and self._image is not None:
            width, height = self._image.width(), self._image.height()
            scale = min(self.width() / width, self.height() / height)
            target = QRectF((self.width() - width * scale) / 2, (self.height() - height * scale) / 2,
                            width * scale, height * scale)
            painter.drawImage(target, self._image)
            return
        titles = {
            "disconnected": "Ready to connect",
            "connecting": "Connecting…",
            "reconnecting": "Reconnecting…",
            "authentication_failed": "Check username and password",
            "stream_unavailable": "Check the camera channel",
            "network_error": "Camera connection interrupted",
            "decoder_error": "Video could not be decoded",
        }
        painter.setPen(QColor("#cbd9e7"))
        painter.setFont(QFont("Segoe UI", max(12, min(24, round(self.height() / 24)))))
        painter.drawText(self.rect().adjusted(20, 20, -20, -20), Qt.AlignmentFlag.AlignCenter,
                         titles.get(status.state.value, "No signal"))

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()

    def _quit(self):
        self.close()


# Retained import for existing developer integration helpers, without kiosk behavior.
KioskWindow = VideoWidget

