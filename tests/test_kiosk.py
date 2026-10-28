"""Normal-window controls and escape routes, exercised with Qt offscreen."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from haunted_tv.config import AppConfig, CredentialError
from haunted_tv.streaming.pyav_capture import CaptureStatus, FramePacket, StreamState
from haunted_tv.ui.kiosk_window import VideoWidget
from haunted_tv.ui.main_window import MainWindow


class Session:
    def __init__(self):
        self.state = StreamState.DISCONNECTED
        self.message = 'No stream connected.'
        self.packet = None
        self.requests = []
        self.reconnects = 0
        self.stopped = False

    def latest_frame(self):
        return self.packet

    def status(self):
        return CaptureStatus(self.state, self.message)

    def connect(self, settings, password_provider=None):
        self.requests.append((settings, password_provider))
        self.state = StreamState.CONNECTING
        self.packet = None

    def disconnect(self):
        self.state = StreamState.DISCONNECTED
        self.packet = None

    def request_reconnect(self):
        self.reconnects += 1

    def stop(self):
        self.stopped = True


class UnavailableVault:
    def get_password(self, url):
        raise CredentialError('Unavailable')

    def set_password(self, url, password):
        raise CredentialError('Unavailable')


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def viewer(app, tmp_path):
    session = Session()
    window = MainWindow(session, AppConfig(), tmp_path / 'config.toml', UnavailableVault())
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window, session
    window.close()
    app.processEvents()


def test_normal_window_has_controls_and_no_automatic_connection(viewer):
    window, session = viewer
    assert not window.isFullScreen()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowModality() == Qt.WindowModality.NonModal
    assert window.cursor().shape() != Qt.CursorShape.BlankCursor
    assert window.connect_button.isVisible()
    assert window.url_edit.isVisible()
    assert session.requests == []
    window.close()
    assert not window.isVisible()
    assert session.stopped


def test_pasted_credentialed_url_is_split_and_never_saved_in_toml(viewer):
    window, session = viewer
    window.url_edit.setText('rtsp://viewer:p%40ss%23%25%3Aword@127.0.0.1:8554/camera')
    assert window.url_edit.text() == 'rtsp://127.0.0.1:8554/camera'
    assert window.username_edit.text() == 'viewer'
    assert window.password_edit.text() == 'p@ss#%:word'
    assert window.password_edit.echoMode() == QLineEdit.EchoMode.Password
    window.connect_button.click()
    settings, provider = session.requests[-1]
    assert settings.url == 'rtsp://viewer@127.0.0.1:8554/camera'
    assert provider() == 'p@ss#%:word'  # Direct session password needs no Windows vault.
    content = window.config_path.read_text()
    assert 'p@ss' not in content and 'p%40ss' not in content


def test_optional_remember_failure_does_not_block_connection(viewer, app):
    window, session = viewer
    window.url_edit.setText('rtsp://viewer@camera.local/live')
    window.password_edit.setText('normal@#%:password')
    window.remember_checkbox.setChecked(True)
    window.connect_camera()
    assert session.requests[-1][1]() == 'normal@#%:password'
    app.processEvents()
    assert 'this session' in window.warning_label.text()


def test_blank_password_uses_saved_vault_credential(viewer):
    window, session = viewer
    class Vault:
        def get_password(self, url):
            return 'saved-secret'
    window.credential_store = Vault()
    window.url_edit.setText('rtsp://viewer@camera.local/live')
    window.connect_camera()
    assert session.requests[-1][1]() == 'saved-secret'


def test_explicit_empty_pasted_password_does_not_load_a_saved_password(viewer):
    window, session = viewer
    window.url_edit.setText('rtsp://viewer:@camera.local/live')
    window.connect_camera()
    assert session.requests[-1][1]() == ''


def test_invalid_input_shows_editable_error_without_echoing_input(viewer):
    window, session = viewer
    window.url_edit.setText('https://viewer:private-secret@camera.local/live')
    window.connect_camera()
    assert not session.requests
    assert window.warning_label.isVisible()
    assert 'private-secret' not in window.warning_label.text()
    assert window.url_edit.isEnabled()


def test_malformed_port_still_moves_pasted_password_into_masked_field(viewer):
    window, session = viewer
    window.url_edit.setText('rtsp://viewer:private%40secret@camera.local:bad/live')
    assert 'secret' not in window.url_edit.text()
    assert window.password_edit.text() == 'private@secret'
    assert window.password_edit.echoMode() == QLineEdit.EchoMode.Password
    window.connect_camera()
    assert not session.requests
    assert window.warning_label.isVisible()


def test_fullscreen_f11_and_escape_restore_editable_window(viewer, app):
    window, _ = viewer
    window.setGeometry(40, 40, 700, 600)
    app.processEvents()
    geometry = window.geometry()
    QTest.keyClick(window, Qt.Key.Key_F11)
    app.processEvents()
    assert window.isFullScreen()
    assert not window.controls.isVisible()
    assert window.leave_fullscreen_button.isVisible()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    QTest.keyClick(window, Qt.Key.Key_Escape)
    app.processEvents()
    assert not window.isFullScreen()
    assert window.controls.isVisible()
    assert window.geometry() == geometry
    assert window.cursor().shape() != Qt.CursorShape.BlankCursor


def test_error_exits_fullscreen_and_shows_specific_reason(viewer, app):
    window, session = viewer
    window.toggle_fullscreen()
    session.state = StreamState.AUTHENTICATION_FAILED
    session.message = 'Camera authentication was rejected.'
    window.refresh_status()
    app.processEvents()
    assert not window.isFullScreen()
    assert window.url_edit.isVisible()
    assert 'authentication was rejected' in window.status_label.text()
    assert 'username and password' in window.status_label.text()
    window.close()
    assert session.stopped


def test_f5_and_disconnect(viewer, app):
    window, session = viewer
    QTest.keyClick(window, Qt.Key.Key_F5)
    app.processEvents()
    assert session.reconnects == 1
    window.disconnect_button.click()
    assert session.state == StreamState.DISCONNECTED


def test_live_frame_fit_and_signal_loss(app):
    worker = Session()
    video = VideoWidget(worker, AppConfig())
    video.resize(640, 480)
    video.show()
    rgb = np.zeros((90, 160, 3), dtype=np.uint8)
    rgb[:, :, 0] = 220
    worker.packet = FramePacket(1, rgb, 1.0)
    worker.state = StreamState.LIVE
    video.refresh()
    image = video.grab().toImage()
    assert image.pixelColor(320, 240).red() == 220
    assert image.pixelColor(320, 10).red() < 10
    worker.packet = None
    worker.state = StreamState.NETWORK_ERROR
    video.refresh()
    assert video._image is None
    video.close()
