"""Capture switching tests; no Qt, camera, socket, or simulated app video."""

import threading
import time

import pytest

from haunted_tv.core.session import CaptureSession
from haunted_tv.streaming.pyav_capture import CaptureStatus, StreamSettings, StreamState


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Capture session did not reach the expected state")


class FakeWorker(threading.Thread):
    def __init__(self, settings, password_provider, factory):
        super().__init__(daemon=True)
        self.settings = settings
        self.password_provider = password_provider
        self.factory = factory
        self.stop_requested = threading.Event()
        self.started = threading.Event()
        self.allow_exit = threading.Event()
        self.allow_exit.set()
        self.frame = object()
        self.reconnects = 0
        self.stop_threads = []
        self.join_threads = []
        self.frame_requested = threading.Event()
        self.allow_frame_read = threading.Event()
        self.allow_frame_read.set()

    def run(self):
        with self.factory.lock:
            self.factory.running += 1
            self.factory.maximum_running = max(self.factory.maximum_running, self.factory.running)
        self.started.set()
        self.stop_requested.wait()
        self.allow_exit.wait()
        with self.factory.lock:
            self.factory.running -= 1

    def stop(self):
        self.stop_threads.append(threading.get_ident())
        self.stop_requested.set()

    def join(self, timeout=None):
        self.join_threads.append(threading.get_ident())
        super().join(timeout)

    def status(self):
        return CaptureStatus(StreamState.LIVE, "Live video.")

    def latest_frame(self):
        self.frame_requested.set()
        self.allow_frame_read.wait(3)
        return self.frame

    def request_reconnect(self):
        self.reconnects += 1


class WorkerFactory:
    def __init__(self):
        self.workers = []
        self.running = 0
        self.maximum_running = 0
        self.lock = threading.Lock()

    def __call__(self, settings, password_provider=None):
        worker = FakeWorker(settings, password_provider, self)
        self.workers.append(worker)
        return worker


def connect_first(session, factory):
    settings = StreamSettings(url="rtsp://first.test/video")
    provider = lambda: "test-only-password"
    session.connect(settings, provider)
    wait_for(lambda: len(factory.workers) == 1 and factory.workers[0].started.is_set())
    first = factory.workers[0]
    wait_for(lambda: session.latest_frame() is first.frame)
    assert first.settings is settings
    assert first.password_provider is provider
    return first


def finish(session, factory):
    for worker in factory.workers:
        worker.allow_exit.set()
        worker.allow_frame_read.set()
    session.stop()
    session.join(3)
    assert not session.is_alive()
    assert all(not worker.is_alive() for worker in factory.workers)


def test_initial_disconnected_session_has_no_worker_and_stops():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    try:
        assert session.is_alive()
        assert session.status().state == StreamState.DISCONNECTED
        assert session.latest_frame() is None
        assert factory.workers == []
    finally:
        finish(session, factory)
    assert session.status().state == StreamState.DISCONNECTED
    with pytest.raises(RuntimeError, match="stopped"):
        session.connect(StreamSettings(url="rtsp://host/video"))


def test_switch_is_nonblocking_coalesces_pending_and_retires_off_gui_thread():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    calling_thread = threading.get_ident()
    try:
        first = connect_first(session, factory)
        first.allow_exit.clear()
        session.connect(StreamSettings(url="rtsp://second.test/video"))
        wait_for(first.stop_requested.is_set)
        session.connect(StreamSettings(url="rtsp://third.test/video"))
        final_settings = StreamSettings(url="rtsp://final.test/video")
        session.connect(final_settings)
        assert session.status().state == StreamState.CONNECTING
        assert session.latest_frame() is None
        assert len(factory.workers) == 1
        assert first.is_alive()
        assert calling_thread not in first.join_threads
        assert calling_thread not in first.stop_threads
        first.allow_exit.set()
        wait_for(lambda: len(factory.workers) == 2 and factory.workers[1].started.is_set())
        final = factory.workers[1]
        wait_for(lambda: session.latest_frame() is final.frame)
        assert final.settings is final_settings
        assert session.status().state == StreamState.LIVE
        assert not first.is_alive()
        assert factory.maximum_running == 1
    finally:
        finish(session, factory)


def test_disconnect_hides_frames_immediately_then_allows_new_connection():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    try:
        first = connect_first(session, factory)
        first.allow_exit.clear()
        session.disconnect()
        assert session.status().state == StreamState.DISCONNECTED
        assert session.latest_frame() is None
        wait_for(first.stop_requested.is_set)
        first.allow_exit.set()
        wait_for(lambda: not first.is_alive())
        assert len(factory.workers) == 1
        session.request_reconnect()
        assert len(factory.workers) == 1
        session.connect(StreamSettings(url="rtsp://new.test/video"))
        wait_for(lambda: len(factory.workers) == 2 and factory.workers[1].started.is_set())
        wait_for(lambda: session.latest_frame() is factory.workers[1].frame)
        assert factory.maximum_running == 1
    finally:
        finish(session, factory)


def test_stop_cancels_pending_connection_and_join_happens_after_call_returns():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    try:
        first = connect_first(session, factory)
        first.allow_exit.clear()
        session.connect(StreamSettings(url="rtsp://never-start.test/video"))
        wait_for(first.stop_requested.is_set)
        session.stop()
        session.join(.01)
        assert session.is_alive()
        assert session.latest_frame() is None
        assert session.status().state == StreamState.DISCONNECTED
        first.allow_exit.set()
        session.join(3)
        assert not session.is_alive()
        assert len(factory.workers) == 1
        session.request_reconnect()
        session.disconnect()
    finally:
        finish(session, factory)


def test_reconnect_delegates_to_current_live_worker():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    try:
        first = connect_first(session, factory)
        session.request_reconnect()
        assert first.reconnects == 1
        assert len(factory.workers) == 1
    finally:
        finish(session, factory)


def test_frame_poll_racing_switch_never_returns_previous_frame():
    factory = WorkerFactory()
    session = CaptureSession(factory)
    polled = []
    reader = None
    try:
        first = connect_first(session, factory)
        first.frame_requested.clear()
        first.allow_frame_read.clear()
        first.allow_exit.clear()
        reader = threading.Thread(target=lambda: polled.append(session.latest_frame()))
        reader.start()
        assert first.frame_requested.wait(2)
        session.connect(StreamSettings(url="rtsp://next.test/video"))
        first.allow_frame_read.set()
        reader.join(2)
        assert polled == [None]
    finally:
        if reader is not None:
            first.allow_frame_read.set()
            reader.join(2)
        finish(session, factory)


def test_worker_initialization_error_is_safe_and_session_can_retry(caplog):
    factory = WorkerFactory()
    calls = 0

    def sometimes_fails(settings, password_provider=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("rtsp://viewer:secret@host/video")
        return factory(settings, password_provider)

    session = CaptureSession(sometimes_fails)
    try:
        session.connect(StreamSettings(url="rtsp://host/video"))
        wait_for(lambda: session.status().state == StreamState.DECODER_ERROR)
        assert "secret" not in session.status().message
        assert "secret" not in caplog.text
        session.request_reconnect()
        wait_for(lambda: len(factory.workers) == 1 and factory.workers[0].started.is_set())
        wait_for(lambda: session.latest_frame() is factory.workers[0].frame)
    finally:
        finish(session, factory)
