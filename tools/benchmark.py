"""Measure real capture throughput only, without saving or displaying frames.

This is NOT a rendering FPS, LAN latency, face inference, or soak certification.
"""
import argparse
from dataclasses import replace
import time
from urllib.parse import urlsplit

from haunted_tv.config import CredentialStore, DEFAULT_CONFIG_PATH, load_config
from haunted_tv.streaming.pyav_capture import CaptureWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 86400:
        parser.error("Duration must be between 1 and 86400 seconds")
    config = load_config(args.config, create=False)
    if not config.stream.url:
        print("FAIL: configure a camera first")
        return 1
    store = CredentialStore()
    provider = (lambda: store.get_password(config.stream.url)) if urlsplit(config.stream.url).username else None
    worker = CaptureWorker(replace(config.stream), password_provider=provider)
    worker.start()
    begin = time.monotonic()
    count = 0
    last_received = None
    largest_gap = 0.0
    dimensions = None
    try:
        while time.monotonic() - begin < args.seconds:
            frame = worker.latest_frame()
            if frame is not None and frame.seq > count:
                if last_received is not None:
                    largest_gap = max(largest_gap, frame.received_at - last_received)
                last_received = frame.received_at
                count = frame.seq
                dimensions = frame.rgb.shape[:2]
            time.sleep(.002)
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.monotonic() - begin
        worker.stop()
        worker.join(config.stream.connect_timeout_s + config.stream.read_timeout_s + 2)
    if worker.is_alive():
        print("FAIL: capture shutdown deadline exceeded")
        return 1
    if dimensions is None:
        print("FAIL: no real frames decoded; use the probe for diagnostics")
        return 1
    print(f"Decoded frames: {count}; observation: {elapsed:.2f}s (includes connection time)")
    print(f"Capture throughput: {count / elapsed:.2f} frames/s; resolution: {dimensions[1]}x{dimensions[0]}")
    print(f"Largest observed inter-frame gap: {largest_gap:.3f}s")
    print("Capture only. Rendering FPS, camera-to-display latency and target-PC acceptance are unmeasured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
