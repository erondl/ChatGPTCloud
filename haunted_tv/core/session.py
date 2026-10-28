"""Qt-free capture switching with one worker and a coalesced pending request.

GUI callers never join a decoder. A supervisor retires the current worker before
starting the latest requested connection, so repeated Connect clicks cannot
create an unbounded set of blocked FFmpeg threads. Switching immediately hides
the previous stream's frames. Call stop() before leaving the GUI event loop,
then join(timeout) after it exits to wait for the configured network timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import threading
from typing import Callable

from haunted_tv.streaming.pyav_capture import (
    CaptureStatus,
    CaptureWorker,
    FramePacket,
    StreamSettings,
    StreamState,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ConnectionRequest:
    generation: int
    settings: StreamSettings = field(repr=False)
    password_provider: Callable[[], str | None] | None = field(repr=False)


class CaptureSession:
    """A reusable session; connect/disconnect/status/frame calls are nonblocking.

    is_alive() describes the supervisor, which stays alive while disconnected
    so another connection can be requested. stop() is terminal; create a new
    session if a completely stopped session needs to be reopened.
    """

    def __init__(self, worker_factory=CaptureWorker) -> None:
        self._worker_factory = worker_factory
        self._condition = threading.Condition()
        self._active = None
        self._active_generation = 0
        self._retiring = None
        self._generation = 0
        self._pending = False
        self._desired: _ConnectionRequest | None = None
        self._last_request: _ConnectionRequest | None = None
        self._stopping = False
        self._fallback = CaptureStatus(StreamState.DISCONNECTED, "No stream connected.")
        self._supervisor = threading.Thread(
            target=self._run, name="capture-session", daemon=True,
        )
        self._supervisor.start()

    def connect(
        self,
        settings: StreamSettings,
        password_provider: Callable[[], str | None] | None = None,
    ) -> None:
        with self._condition:
            if self._stopping:
                raise RuntimeError("The capture session has been stopped.")
            self._generation += 1
            request = _ConnectionRequest(self._generation, settings, password_provider)
            self._last_request = self._desired = request
            self._pending = True
            self._fallback = CaptureStatus(StreamState.CONNECTING, "Connecting to the selected stream.")
            self._condition.notify()

    def disconnect(self) -> None:
        """Hide the image now, retiring the decoder in the supervisor thread."""
        with self._condition:
            if self._stopping:
                return
            self._generation += 1
            self._desired = self._last_request = None
            self._pending = True
            self._fallback = CaptureStatus(StreamState.DISCONNECTED, "Stream disconnected.")
            self._condition.notify()

    def _visible_worker(self):
        if (
            not self._stopping and not self._pending
            and self._active_generation == self._generation
        ):
            return self._active
        return None

    def status(self) -> CaptureStatus:
        with self._condition:
            worker = self._visible_worker()
            fallback = self._fallback
        if worker is None:
            return fallback
        result = worker.status()
        with self._condition:
            return result if self._visible_worker() is worker else self._fallback

    def latest_frame(self) -> FramePacket | None:
        with self._condition:
            worker = self._visible_worker()
        if worker is None:
            return None
        result = worker.latest_frame()
        # A Connect/Stop can race with a poll. Recheck before returning a frame
        # so the previous camera never reappears after the user switches away.
        with self._condition:
            return result if self._visible_worker() is worker else None

    def request_reconnect(self) -> None:
        with self._condition:
            if self._stopping or self._pending:
                return
            worker = self._visible_worker()
            request = self._last_request
            if worker is None or not worker.is_alive():
                if request is not None:
                    self._generation += 1
                    self._desired = self._last_request = _ConnectionRequest(
                        self._generation, request.settings, request.password_provider,
                    )
                    self._pending = True
                    self._fallback = CaptureStatus(StreamState.CONNECTING, "Reconnecting to the selected stream.")
                    self._condition.notify()
                return
        worker.request_reconnect()

    def stop(self) -> None:
        """Signal all owned workers without joining them on the calling thread."""
        with self._condition:
            self._stopping = True
            self._generation += 1
            self._pending = False
            self._desired = self._last_request = None
            self._fallback = CaptureStatus(StreamState.DISCONNECTED, "Capture stopped.")
            workers = (self._active, self._retiring)
            self._condition.notify()
        for worker in workers:
            if worker is not None:
                worker.stop()

    def join(self, timeout: float | None = None) -> None:
        """Wait after the GUI loop exits; network timeouts bound normal shutdown."""
        self._supervisor.join(timeout)

    def is_alive(self) -> bool:
        return self._supervisor.is_alive()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._stopping or self._pending)
                worker = self._active
                self._active = None
                self._retiring = worker

            if worker is not None:
                worker.stop()
                worker.join()

            with self._condition:
                self._retiring = None
                if self._stopping:
                    return
                # Read only after retirement. Every Connect received while the
                # old decoder was blocked has collapsed into this latest slot.
                request = self._desired
                self._desired = None
                self._pending = False
            if request is None:
                continue

            try:
                worker = self._worker_factory(
                    request.settings, password_provider=request.password_provider,
                )
            except Exception:
                with self._condition:
                    if request.generation == self._generation:
                        self._fallback = CaptureStatus(
                            StreamState.DECODER_ERROR, "The capture worker could not be initialized.",
                        )
                LOGGER.error("Capture worker initialization failed.")
                continue

            with self._condition:
                if self._stopping:
                    return
                if request.generation != self._generation:
                    # The factory did not open a stream; only a started worker
                    # may own FFmpeg resources. Discard this obsolete request.
                    continue
                try:
                    worker.start()
                except Exception:
                    self._fallback = CaptureStatus(
                        StreamState.DECODER_ERROR, "The capture worker could not be started.",
                    )
                    LOGGER.error("Capture worker startup failed.")
                    continue
                self._active = worker
                self._active_generation = request.generation

