"""Editable connection form with freely escapable fullscreen viewing."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from haunted_tv import __version__
from haunted_tv.config import CredentialError, CredentialStore, save_config
from haunted_tv.config.connection import parse_connection_input
from haunted_tv.core.logging_setup import register_secret
from haunted_tv.core.power import SleepGuard
from haunted_tv.streaming.pyav_capture import StreamSettings
from haunted_tv.ui.kiosk_window import VideoWidget


class _Notice(QObject):
    warning = Signal(str)


class MainWindow(QWidget):
    def __init__(self, session, config, config_path: Path, credential_store=None):
        super().__init__()
        self.session = session
        self.config = config
        self.config_path = config_path
        self.credential_store = credential_store or CredentialStore()
        self._sleep_guard = None
        self._window_geometry = None
        self._was_maximized = False
        self._imported_empty_password = False
        self._notice = _Notice(self)
        self._notice.warning.connect(self._show_warning)
        self.setWindowTitle(f"Haunted TV {__version__}")
        # Native, nonmodal window: no topmost flag, grabs, hidden cursor or PIN lock.
        available = self.screen().availableGeometry()
        self.resize(min(1100, available.width() - 40), min(760, available.height() - 60))
        self.setMinimumSize(680, 480)
        self.setStyleSheet("""
            MainWindow { background: #101720; color: #dce5ef; }
            QLabel, QCheckBox { color: #dce5ef; }
            QLineEdit, QComboBox { background: #1b2735; color: #ecf3fb;
                border: 1px solid #3e5064; border-radius: 5px; padding: 7px; }
            QPushButton { background: #26384b; color: #edf4fc; border: 1px solid #4a6078;
                border-radius: 5px; padding: 8px 15px; }
            QPushButton:hover { background: #344c65; }
            QPushButton#connect { background: #226c61; border-color: #329184; }
            QFrame#panel { background: #141e2a; border-radius: 7px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        self.controls = QFrame(self)
        self.controls.setObjectName("panel")
        panel = QVBoxLayout(self.controls)
        heading = QLabel("Haunted TV  ·  Live camera", self.controls)
        heading.setStyleSheet("font-size: 20px; font-weight: 600;")
        panel.addWidget(heading)
        form = QFormLayout()
        self.url_edit = QLineEdit(self.controls)
        self.url_edit.setPlaceholderText("Paste an RTSP URL, including credentials if needed")
        self.url_edit.setClearButtonEnabled(True)
        form.addRow("RTSP URL", self.url_edit)
        credentials = QHBoxLayout()
        self.username_edit = QLineEdit(self.controls)
        self.username_edit.setPlaceholderText("Username")
        self.password_edit = QLineEdit(self.controls)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password · blank uses saved credential")
        self.password_edit.textEdited.connect(self._password_edited)
        self.transport_combo = QComboBox(self.controls)
        self.transport_combo.addItems(["TCP", "UDP"])
        self.transport_combo.setCurrentText(config.stream.transport.upper())
        credentials.addWidget(self.username_edit, 2)
        credentials.addWidget(self.password_edit, 3)
        credentials.addWidget(self.transport_combo, 1)
        form.addRow("Credentials", credentials)
        panel.addLayout(form)
        self.remember_checkbox = QCheckBox("Remember password in Windows Credential Manager", self.controls)
        self.remember_checkbox.setEnabled(sys.platform == "win32")
        panel.addWidget(self.remember_checkbox)
        actions = QHBoxLayout()
        self.connect_button = QPushButton("Connect", self.controls)
        self.connect_button.setObjectName("connect")
        self.connect_button.clicked.connect(self.connect_camera)
        self.disconnect_button = QPushButton("Disconnect", self.controls)
        self.disconnect_button.clicked.connect(session.disconnect)
        self.fullscreen_button = QPushButton("Full screen  ·  F11", self.controls)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.exit_button = QPushButton("Exit", self.controls)
        self.exit_button.clicked.connect(self.close)
        for button in (self.connect_button, self.disconnect_button, self.fullscreen_button):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.exit_button)
        panel.addLayout(actions)
        self.warning_label = QLabel("", self.controls)
        self.warning_label.setTextFormat(Qt.TextFormat.PlainText)
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #f3bf7d;")
        self.warning_label.hide()
        panel.addWidget(self.warning_label)
        root.addWidget(self.controls)
        self.video = VideoWidget(session, config, self)
        root.addWidget(self.video, 1)
        self.status_label = QLabel("Ready. Paste your camera URL and click Connect.", self)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.fullscreen_controls = QFrame(self.video)
        overlay = QHBoxLayout(self.fullscreen_controls)
        overlay.setContentsMargins(0, 0, 0, 0)
        self.leave_fullscreen_button = QPushButton("Exit fullscreen  ·  Esc", self.fullscreen_controls)
        self.leave_fullscreen_button.clicked.connect(self.leave_fullscreen)
        overlay.addWidget(self.leave_fullscreen_button)
        self.fullscreen_controls.adjustSize()
        self.fullscreen_controls.move(12, 12)
        self.fullscreen_controls.hide()
        self._shortcuts = []
        for sequence, callback in (("F11", self.toggle_fullscreen), ("Esc", self.leave_fullscreen),
                                   ("F5", session.request_reconnect), ("Ctrl+Alt+Q", self.close)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self.password_edit.returnPressed.connect(self.connect_camera)
        self.url_edit.returnPressed.connect(self.connect_camera)
        self.url_edit.textChanged.connect(self._import_pasted_credentials)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self.refresh_status)
        self._status_timer.start(150)
        if config.stream.url:
            self.url_edit.setText(config.stream.url)

    def _import_pasted_credentials(self, value):
        """Hide userinfo even if the host, port or remaining path is malformed."""
        self._imported_empty_password = False
        scheme, separator, remainder = value.partition("://")
        if not separator:
            return
        authority, slash, path = remainder.partition("/")
        userinfo, at, host = authority.rpartition("@")
        if not at:
            return
        username, colon, password = userinfo.partition(":")
        if colon:
            self.password_edit.setText(unquote(password))
            self._imported_empty_password = password == ""
        self.username_edit.setText(unquote(username))
        address = scheme + separator + host + slash + path
        self.url_edit.blockSignals(True)
        self.url_edit.setText(address)
        self.url_edit.blockSignals(False)

    def _password_edited(self, value):
        self._imported_empty_password = False

    def _show_warning(self, message):
        self.warning_label.setText(message)
        self.warning_label.show()

    def connect_camera(self):
        self.warning_label.hide()
        try:
            connection = parse_connection_input(self.url_edit.text().strip(),
                                                self.username_edit.text(), self.password_edit.text())
            if connection.password is None and self._imported_empty_password:
                connection = replace(connection, password="")
        except ValueError:
            self._show_warning("Enter a valid rtsp:// camera URL. Paste a full URL or use the username and password fields.")
            return
        self.config.stream.url = connection.url
        self.config.stream.transport = self.transport_combo.currentText().lower()
        try:
            save_config(self.config, self.config_path)
        except (OSError, ValueError):
            self._show_warning("Settings could not be saved. This connection will still run for this session.")
        if connection.password is not None:
            register_secret(connection.password)
        remember = self.remember_checkbox.isChecked()
        store = self.credential_store
        notice = self._notice
        password = connection.password
        safe_url = connection.url
        username_present = bool(urlsplit(safe_url).username)

        # Vault work is performed by capture, not the GUI thread.
        def password_provider():
            nonlocal remember
            if password is not None:
                if remember:
                    remember = False
                    try:
                        store.set_password(safe_url, password)
                    except CredentialError:
                        notice.warning.emit("Password could not be remembered. Using it for this session; video can still connect.")
                return password
            if username_present:
                try:
                    return store.get_password(safe_url)
                except CredentialError:
                    notice.warning.emit("Saved password is unavailable. Enter your camera password and click Connect.")
                    raise
            return None

        self.session.connect(StreamSettings(**vars(self.config.stream)), password_provider=password_provider)
        self.status_label.setText("Connecting… You can edit settings, disconnect or close at any time.")
        self.video.refresh()

    def refresh_status(self):
        status = self.session.status()
        state = status.state.value
        hints = {
            "disconnected": "Ready. Paste your camera URL and click Connect.",
            "authentication_failed": "Check username and password, then click Connect. A separately entered password uses its normal characters.",
            "stream_unavailable": "Check the stream channel/path and camera permissions, then click Connect.",
            "network_error": "Check camera power, address and network. Automatic retry is active.",
            "decoder_error": "Try the camera's H.264 substream and TCP transport, then click Connect.",
        }
        prefix = state.replace("_", " ").capitalize()
        self.status_label.setText(f"{prefix}: {status.message}  {hints.get(state, '')}")
        if state in {"authentication_failed", "stream_unavailable", "decoder_error", "network_error"} and self.isFullScreen():
            self.leave_fullscreen()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.leave_fullscreen()
            return
        self._window_geometry = self.saveGeometry()
        self._was_maximized = self.isMaximized()
        self.controls.hide()
        self.status_label.hide()
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.showFullScreen()
        self.fullscreen_controls.show()
        self.fullscreen_controls.raise_()
        self._sleep_guard = SleepGuard()
        self._sleep_guard.start()

    def leave_fullscreen(self):
        if not self.isFullScreen():
            return
        self.showNormal()
        if self._window_geometry is not None:
            self.restoreGeometry(self._window_geometry)
        if self._was_maximized:
            self.showMaximized()
        self.controls.show()
        self.status_label.show()
        self.fullscreen_controls.hide()
        self.layout().setContentsMargins(16, 14, 16, 14)
        if self._sleep_guard is not None:
            self._sleep_guard.stop()
            self._sleep_guard = None

    def closeEvent(self, event):
        self._status_timer.stop()
        self.video._timer.stop()
        self.password_edit.clear()
        self.session.stop()
        if self._sleep_guard is not None:
            self._sleep_guard.stop()
            self._sleep_guard = None
        event.accept()

