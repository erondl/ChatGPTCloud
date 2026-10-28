"""Opt-in, loopback-only RTSP test source. Never imported by the application.

Requires MediaMTX (https://github.com/bluenviron/mediamtx) and FFmpeg with libx264.
The generated colour pattern exercises the real RTSP/FFmpeg pipeline; it is not
evidence of camera compatibility or target-PC acceptance.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class LocalRTSPSource:
    """Owns only the server/publisher processes this instance starts."""

    def __init__(self, mediamtx: str | Path, port: int | None = None):
        self.mediamtx = Path(mediamtx).resolve()
        self.port = port or available_port()
        self.url = f"rtsp://127.0.0.1:{self.port}/haunted-test"
        self.server: subprocess.Popen | None = None
        self.publisher: subprocess.Popen | None = None
        self._temporary: tempfile.TemporaryDirectory | None = None
        self._logs = None

    def __enter__(self) -> "LocalRTSPSource":
        if not self.mediamtx.is_file():
            raise FileNotFoundError("Supply the path to the official MediaMTX binary")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("FFmpeg with libx264 must be installed")
        self._temporary = tempfile.TemporaryDirectory(prefix="haunted-tv-rtsp-")
        directory = Path(self._temporary.name)
        config = directory / "mediamtx.yml"
        config.write_text(
            "logLevel: warn\n"
            "rtsp: yes\n"
            f"rtspAddress: 127.0.0.1:{self.port}\n"
            "rtspTransports: [tcp]\n"
            "rtmp: no\nhls: no\nwebrtc: no\nsrt: no\n"
            "api: no\nmetrics: no\npprof: no\nplayback: no\n"
            "paths:\n  all_others:\n    source: publisher\n",
            encoding="utf-8",
        )
        self._logs = (directory / "source.log").open("wb")
        try:
            self.server = subprocess.Popen(
                [str(self.mediamtx), str(config)],
                stdin=subprocess.DEVNULL, stdout=self._logs, stderr=self._logs,
            )
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if self.server.poll() is not None:
                    raise RuntimeError("MediaMTX startup failed: " + self.diagnostics())
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.05)
            else:
                raise RuntimeError("MediaMTX did not listen on its loopback RTSP port")
            self.start_publisher()
            return self
        except BaseException:
            self.close()
            raise

    def start_publisher(self) -> None:
        if self.publisher is not None and self.publisher.poll() is None:
            return
        self.publisher = subprocess.Popen(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-re", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25",
                "-an", "-c:v", "libx264", "-preset", "ultrafast",
                "-tune", "zerolatency", "-g", "25", "-pix_fmt", "yuv420p",
                "-f", "rtsp", "-rtsp_transport", "tcp", self.url,
            ],
            stdin=subprocess.DEVNULL, stdout=self._logs, stderr=self._logs,
        )
        # A listening server is not yet a published stream. Wait for real SDP
        # before returning, so an immediate diagnostic probe has a valid source.
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.publisher.poll() is not None:
                raise RuntimeError("FFmpeg publisher failed: " + self.diagnostics())
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=.3) as connection:
                    connection.settimeout(.3)
                    connection.sendall((f"DESCRIBE {self.url} RTSP/1.0\r\n"
                                        "CSeq: 1\r\nAccept: application/sdp\r\n\r\n").encode("ascii"))
                    response = connection.recv(4096)
                    if response.startswith(b"RTSP/1.0 200 "):
                        return
            except OSError:
                pass
            time.sleep(.05)
        raise RuntimeError("FFmpeg did not publish a video session before its deadline")

    def stop_publisher(self) -> None:
        stop_process(self.publisher)
        self.publisher = None

    def diagnostics(self) -> str:
        if self._temporary is None:
            return "No source logs"
        return (Path(self._temporary.name) / "source.log").read_text(
            encoding="utf-8", errors="replace"
        )[-4000:]

    def close(self) -> None:
        self.stop_publisher()
        stop_process(self.server)
        self.server = None
        if self._logs is not None:
            self._logs.close()
            self._logs = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def __exit__(self, *_exc) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mediamtx", required=True, help="Path to MediaMTX executable")
    parser.add_argument("--port", type=int, default=8554)
    args = parser.parse_args()
    with LocalRTSPSource(args.mediamtx, args.port) as source:
        print(f"TEST PATTERN ONLY: {source.url}\nCtrl+C stops both test processes.")
        try:
            while source.server.poll() is None and source.publisher.poll() is None:
                time.sleep(.5)
            raise RuntimeError("RTSP source stopped: " + source.diagnostics())
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
