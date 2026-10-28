"""Bounded, latest-frame-only RTSP capture in one worker thread.

Only the capture thread owns and closes its FFmpeg container. Network I/O uses
PyAV's interrupt timeout; a stop/reconnect request may therefore take up to the
configured connect/read timeout to complete. No frame queue, recording, camera
audio decode, telemetry, or frame persistence is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import threading
import time
from typing import Callable

import av
import numpy as np

from .rtsp_validator import InvalidRTSPURL, redact_sensitive, with_password


LOGGER = logging.getLogger(__name__)


class StreamState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    AUTHENTICATION_FAILED = "authentication_failed"
    STREAM_UNAVAILABLE = "stream_unavailable"
    NETWORK_ERROR = "network_error"
    DECODER_ERROR = "decoder_error"


@dataclass(frozen=True)
class StreamSettings:
    url: str = field(default="", repr=False)
    transport: str = "tcp"
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 8.0
    reconnect_max_backoff_s: float = 30.0
    max_auth_failures: int = 3


@dataclass(frozen=True)
class FramePacket:
    seq: int
    rgb: np.ndarray = field(repr=False)
    received_at: float


@dataclass(frozen=True)
class CaptureStatus:
    state: StreamState
    message: str
    attempts: int = 0


class NoFramesError(Exception):
    """The stream is open but its decoded-frame watchdog has expired."""


class CredentialAccessError(Exception):
    """The configured credential backend is unavailable."""


def classify_failure(error: BaseException) -> tuple[StreamState, str]:
    """Classify internally, returning only fixed, credential-free messages."""
    if isinstance(error, InvalidRTSPURL):
        return StreamState.STREAM_UNAVAILABLE, "Invalid RTSP configuration."
    if isinstance(error, NoFramesError):
        return StreamState.NETWORK_ERROR, "No decoded frame before the stall deadline."
    if isinstance(error, CredentialAccessError):
        return StreamState.AUTHENTICATION_FAILED, "Credential Manager access failed; run secure setup."
    if isinstance(error, (av.error.HTTPUnauthorizedError, av.error.HTTPForbiddenError)):
        return StreamState.AUTHENTICATION_FAILED, "Camera authentication was rejected."
    if isinstance(error, av.error.HTTPNotFoundError):
        return StreamState.STREAM_UNAVAILABLE, "The requested video channel is unavailable."
    # FFmpeg builds differ in which exception class wraps RTSP response codes.
    # Its raw error text is inspected only in memory and never logged/stored.
    description = redact_sensitive(getattr(error, "strerror", None) or str(error)).lower()
    status = re.search(r"\b(?:rtsp/\d\.\d\s+|(?:describe|options|setup|play)\s+failed:\s*|server returned\s+)(401|403|404)\b", description)
    if status and status.group(1) in {"401", "403"}:
        return StreamState.AUTHENTICATION_FAILED, "Camera authentication was rejected."
    if (status and status.group(1) == "404") or "no video stream" in description:
        return StreamState.STREAM_UNAVAILABLE, "The requested video channel is unavailable."
    if isinstance(error, av.error.InvalidDataError):
        return StreamState.DECODER_ERROR, "The video decoder could not produce a frame."
    name = type(error).__name__.lower()
    if isinstance(error, OSError) or any(term in name for term in ("timeout", "exiterror", "connection")):
        return StreamState.NETWORK_ERROR, "Camera network access failed or timed out."
    return StreamState.DECODER_ERROR, "The video decoder could not produce a frame."


class CaptureWorker(threading.Thread):
    """Poll .status() and .latest_frame() from the GUI; neither call blocks on I/O."""

    def __init__(
        self,
        settings: StreamSettings,
        password_provider: Callable[[], str | None] | None = None,
    ) -> None:
        super().__init__(name="rtsp-capture", daemon=True)
        self.settings = settings
        self.password_provider = password_provider or (lambda: None)
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._reconnect_requested = threading.Event()
        self._wake = threading.Event()
        self._packet: FramePacket | None = None
        self._sequence = 0
        self._status = CaptureStatus(StreamState.DISCONNECTED, "Stream has not started.")
        self._attempts = 0
        self._auth_failures = 0

    def stop(self) -> None:
        self._stop_requested.set()
        self._wake.set()

    def request_reconnect(self) -> None:
        self._reconnect_requested.set()
        self._wake.set()

    def latest_frame(self) -> FramePacket | None:
        with self._lock:
            return self._packet

    def status(self) -> CaptureStatus:
        with self._lock:
            return self._status

    def _set_status(self, state: StreamState, message: str) -> None:
        with self._lock:
            changed = self._status.state != state
            self._status = CaptureStatus(state, message, self._attempts)
            if state != StreamState.LIVE:
                self._packet = None
        if changed:
            LOGGER.info("Capture %s: %s", state.value, message)

    def _publish(self, rgb: np.ndarray) -> None:
        rgb.flags.writeable = False
        with self._lock:
            self._sequence += 1
            self._packet = FramePacket(self._sequence, rgb, time.monotonic())
        self._set_status(StreamState.LIVE, "Live video.")

    def _wait(self, seconds: float | None) -> None:
        self._wake.wait(seconds)
        self._wake.clear()

    def run(self) -> None:
        # FFmpeg can print the credential-bearing input URL in native logs. Our
        # diagnostics use fixed messages, so suppress native logs process-wide.
        av.logging.set_level(None)
        failures = 0
        while not self._stop_requested.is_set():
            if self._reconnect_requested.is_set():
                self._reconnect_requested.clear()
                self._auth_failures = 0
                failures = 0
            if not self.settings.url:
                self._set_status(StreamState.DISCONNECTED, "No RTSP channel configured.")
                self._wait(None)
                continue
            self._attempts += 1
            self._set_status(
                StreamState.CONNECTING if failures == 0 else StreamState.RECONNECTING,
                "Connecting to the configured camera.",
            )
            container = None
            try:
                try:
                    password = self.password_provider()
                except Exception:
                    raise CredentialAccessError() from None
                address = with_password(self.settings.url, password)
                password = None
                container = av.open(
                    address,
                    mode="r",
                    options={
                        "rtsp_transport": self.settings.transport,
                        "fflags": "nobuffer",
                        "flags": "low_delay",
                        "reorder_queue_size": "0",
                    },
                    timeout=(self.settings.connect_timeout_s, self.settings.read_timeout_s),
                )
                address = None
                if not container.streams.video:
                    raise ValueError("No video stream")
                video = container.streams.video[0]
                video.codec_context.thread_count = 2
                video.thread_type = "SLICE"
                last_decoded = time.monotonic()
                for packet in container.demux(video):
                    if self._stop_requested.is_set() or self._reconnect_requested.is_set():
                        break
                    if time.monotonic() - last_decoded > self.settings.read_timeout_s:
                        raise NoFramesError()
                    for frame in packet.decode():
                        if self._stop_requested.is_set() or self._reconnect_requested.is_set():
                            break
                        self._publish(frame.to_ndarray(format="rgb24"))
                        last_decoded = time.monotonic()
                        failures = 0
                        self._auth_failures = 0
                if not self._stop_requested.is_set() and not self._reconnect_requested.is_set():
                    raise NoFramesError()
            except Exception as error:
                if not self._stop_requested.is_set() and not self._reconnect_requested.is_set():
                    state, message = classify_failure(error)
                    self._set_status(state, message)
                    failures += 1
                    if state == StreamState.AUTHENTICATION_FAILED:
                        self._auth_failures += 1
            finally:
                # Ownership never crosses threads, including stop/reconnect.
                if container is not None:
                    try:
                        container.close()
                    except Exception:
                        LOGGER.warning("Capture container cleanup failed.")
                address = None
            if self._stop_requested.is_set():
                break
            if self._reconnect_requested.is_set():
                continue
            if self._auth_failures >= self.settings.max_auth_failures:
                self._set_status(
                    StreamState.AUTHENTICATION_FAILED,
                    "Authentication retry limit reached; correct credentials and force reconnect.",
                )
                self._wait(None)
            else:
                delay = min(self.settings.reconnect_max_backoff_s, 2.0 ** min(failures - 1, 20))
                self._wait(max(0.1, delay))
        self._set_status(StreamState.DISCONNECTED, "Capture stopped.")

