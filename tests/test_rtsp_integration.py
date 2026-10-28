"""Opt-in real RTSP integration. No real camera or physical display is tested."""
from __future__ import annotations

import os
import shutil
import time

import pytest

from tools.local_rtsp import LocalRTSPSource

pytestmark = pytest.mark.integration

def wait_for(predicate, timeout=15, detail=lambda: ""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.05)
    pytest.fail("RTSP condition timed out: " + detail())


@pytest.mark.skipif(
    not os.environ.get("HAUNTED_TV_MEDIAMTX") or not shutil.which("ffmpeg"),
    reason="Set HAUNTED_TV_MEDIAMTX to MediaMTX; FFmpeg with libx264 is required",
)
def test_real_rtsp_decode_and_recover_after_publisher_loss():
    from haunted_tv.streaming.pyav_capture import CaptureWorker, StreamSettings

    with LocalRTSPSource(os.environ["HAUNTED_TV_MEDIAMTX"]) as source:
        worker = CaptureWorker(StreamSettings(
            url=source.url, connect_timeout_s=2, read_timeout_s=2,
            reconnect_max_backoff_s=2,
        ))
        worker.start()
        try:
            first = wait_for(worker.latest_frame, detail=source.diagnostics)
            assert first.rgb.shape == (360, 640, 3)
            assert first.rgb.dtype.name == "uint8"
            assert int(first.rgb.max()) - int(first.rgb.min()) > 150
            second = wait_for(
                lambda: (frame if (frame := worker.latest_frame()) is not None
                         and frame.seq > first.seq else None),
                detail=source.diagnostics,
            )
            assert second.received_at >= first.received_at

            source.stop_publisher()
            wait_for(
                lambda: worker.status().state.value != "live", timeout=12,
                detail=lambda: str(worker.status()),
            )
            before_resume = worker.latest_frame()
            resume_time = time.monotonic()
            source.start_publisher()
            recovered = wait_for(
                lambda: (frame if (frame := worker.latest_frame()) is not None
                         and frame.received_at > resume_time
                         and (before_resume is None or frame.seq > before_resume.seq)
                         else None),
                timeout=20, detail=lambda: str(worker.status()) + source.diagnostics(),
            )
            assert recovered.rgb.shape == (360, 640, 3)
        finally:
            worker.stop()
            worker.join(timeout=8)
            assert not worker.is_alive(), "Capture did not stop within configured timeouts"


@pytest.mark.skipif(
    not os.environ.get("HAUNTED_TV_MEDIAMTX") or not shutil.which("ffmpeg"),
    reason="Set HAUNTED_TV_MEDIAMTX to MediaMTX; FFmpeg with libx264 is required",
)
def test_real_probe_and_capture_benchmark(tmp_path, capsys):
    from haunted_tv.config import AppConfig, save_config
    from tools.probe import main as probe
    from tools.benchmark import main as benchmark
    with LocalRTSPSource(os.environ["HAUNTED_TV_MEDIAMTX"]) as source:
        config = AppConfig()
        config.stream.url = source.url
        config.stream.connect_timeout_s = 3
        config.stream.read_timeout_s = 3
        path = tmp_path / "local-test.toml"
        save_config(config, path)
        assert probe(["--config", str(path)]) == 0
        output = capsys.readouterr().out
        assert "DESCRIBE/SDP: PASS" in output
        assert "MEDIA: PASS" in output
        assert source.url not in output
        assert benchmark(["--config", str(path), "--seconds", "4"]) == 0
        assert "Capture throughput:" in capsys.readouterr().out


@pytest.mark.skipif(
    not os.environ.get("HAUNTED_TV_MEDIAMTX") or not shutil.which("ffmpeg"),
    reason="Set HAUNTED_TV_MEDIAMTX to MediaMTX; FFmpeg with libx264 is required",
)
def test_real_rtsp_reaches_qt_widget():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from haunted_tv.config import AppConfig
    from haunted_tv.streaming.pyav_capture import CaptureWorker, StreamSettings
    from haunted_tv.ui.kiosk_window import KioskWindow
    app = QApplication.instance() or QApplication([])
    with LocalRTSPSource(os.environ["HAUNTED_TV_MEDIAMTX"]) as source:
        worker = CaptureWorker(StreamSettings(url=source.url, connect_timeout_s=3, read_timeout_s=3))
        window = KioskWindow(worker, AppConfig())
        window.resize(800, 600)
        worker.start()
        window.show()
        try:
            deadline = time.monotonic() + 12
            while window._image is None and time.monotonic() < deadline:
                QTest.qWait(25)
                # Qt's qWait does not release the Python GIL on every platform.
                time.sleep(.005)
            assert window._image is not None
            assert (window._image.width(), window._image.height()) == (640, 360)
            assert worker.status().state.value == "live"
            # Render the genuine streamed pattern in memory, never save a camera image.
            rendered = window.grab().toImage()
            colors = {rendered.pixelColor(x, 300).rgb() for x in range(80, 720, 20)}
            assert len(colors) > 4
        finally:
            window._quit()
            worker.stop()
            worker.join(8)
            assert not worker.is_alive()


@pytest.mark.skipif(
    not os.environ.get("HAUNTED_TV_MEDIAMTX") or not shutil.which("ffmpeg"),
    reason="Set HAUNTED_TV_MEDIAMTX to MediaMTX; FFmpeg with libx264 is required",
)
def test_connection_form_live_fullscreen_error_recovery_and_close(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from haunted_tv.config import AppConfig
    from haunted_tv.core.session import CaptureSession
    from haunted_tv.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    def poll(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QTest.qWait(20)
            time.sleep(.005)
            if predicate():
                return
        pytest.fail("The live viewer did not reach the expected state")

    with LocalRTSPSource(os.environ["HAUNTED_TV_MEDIAMTX"]) as source:
        config = AppConfig()
        config.stream.connect_timeout_s = 2
        config.stream.read_timeout_s = 2
        config.stream.reconnect_max_backoff_s = 2
        session = CaptureSession()
        window = MainWindow(session, config, tmp_path / "viewer.toml")
        window.show()
        try:
            assert session.latest_frame() is None
            assert session.status().state.value == "disconnected"
            window.url_edit.setText(source.url)
            window.connect_button.click()
            poll(lambda: session.status().state.value == "live" and window.video._image is not None)
            assert not window.isFullScreen()
            window.fullscreen_button.click()
            assert window.isFullScreen()
            source.stop_publisher()
            poll(lambda: not window.isFullScreen())
            assert window.url_edit.isVisible() and window.connect_button.isEnabled()
            assert window.status_label.text()
            source.start_publisher()
            poll(lambda: session.status().state.value == "live" and window.video._image is not None)
            window.disconnect_button.click()
            assert session.latest_frame() is None
            window.close()
            assert not window.isVisible()
        finally:
            window.close()
            session.join(8)
            assert not session.is_alive()
