# Phase A test report — 2026-10-28

## Scope and release status

Haunted TV 0.1.0 implements **Phase A only**. The supplied specification explicitly
requires target-PC acceptance before Phase B starts. That gate is **pending**.
The operator reports that the camera already works with their existing local
Python player. This is useful source evidence, not acceptance of this new kiosk.

## Executed in this cloud environment

Linux x86-64, CPython 3.12.14, PySide6/Qt 6.9.1 (offscreen platform),
PyAV 16.0.1, NumPy 2.2.6. Developer integration uses system FFmpeg 7.1.5
with libx264 and MediaMTX 1.12.3 on loopback. No real camera credentials were used.

Run from `/workspace/ChatGPTCloud`:

```sh
QT_QPA_PLATFORM=offscreen \
HAUNTED_TV_NETWORK_TESTS=1 \
HAUNTED_TV_MEDIAMTX=/workspace/haunted-tv-tools/mediamtx \
.venv/bin/python -m pytest -q
```

**Final result: 76 passed, 0 failed, 0 skipped in 22.88 seconds.** This is test
execution time, not a video performance measurement. `pip check`, CLI entry-point
smokes and Python byte-compilation also passed.

The optional tests require permission to bind/connect loopback sockets. Without
those two environment variables the five real network/media tests are skipped;
a default run alone must not be described as real RTSP validation.

| Capability | Evidence and limits |
|---|---|
| Pinned dependencies | Installed from binary wheels; `pip check` passed on this Linux/Python version. No verification was disabled. Windows installation remains unexecuted. |
| Real RTSP decode | MediaMTX + FFmpeg generated 640×360 H.264 video; PyAV yielded nonuniform uint8 RGB frames with advancing sequence numbers. |
| Loss and recovery | Stopped the local publisher, observed non-live state, restarted it, observed newer live frames, and verified bounded worker shutdown. This is not a physical cable-unplug test. |
| Full media-to-render path | Decoded the actual RTSP test pattern into the Qt widget and checked the in-memory rendered image. Offscreen only; no camera images saved. |
| Connection probe | Real DNS/TCP/OPTIONS/DESCRIBE/SDP and decoded-video checks passed against local RTSP. Authenticated SDP/SETUP/RTP are inferred together from media, not independently timed. |
| Benchmark tool | Executed against the local stream, producing a real capture-throughput report. No reference-PC performance claim follows. |
| Special-character passwords | URL roundtrip tests plus actual FFmpeg Basic-auth request confirmed exact `@ # % :` password bytes, encoded once. The test receiver deliberately returns 404 after validating the password, not video. NVR login remains unverified. |
| Wrong credentials | Actual FFmpeg authentication handshakes stopped after exactly three rejected attempts and remained paused; unit tests verified explicit reconnect resumes attempts. |
| Kiosk controls | Qt tests verified frameless/always-on-top flags, hidden panel/cursor, F5 reconnect, Esc/ordinary close blocked, wrong PIN rejected, correct PIN exits, and attempt throttling. Physical Windows shortcuts/display still need verification. |
| Lifecycle and sleep guard | Real application no-signal startup/exit and worker cleanup passed offscreen. Windows API call/restore contract tested with a mock; actual Windows power behavior unverified. |
| Configuration/security | Missing/malformed sections, wrong types, bounds, Unicode roundtrip, password/token rejection, salted PIN verification and credential-backend failure tests passed. Windows vault tested with mocks, not a real vault. |
| Log privacy | Tests verified URL and registered-password redaction, including exception text; rotating-file limits checked. Native FFmpeg logging disabled. No production frame/audio persistence or telemetry is implemented. |
| Signal-loss motion | Qt image check verified `reduce_motion=true` freezes static. No CRT flashes or scare effects exist in Phase A. |

The MediaMTX release archive was verified against its official SHA-256 file:
`450d1172bf6708cbd630eada115ccfc33453227e16750369113d1dfe34f876d8`
(`mediamtx_v1.12.3_linux_amd64.tar.gz`). No MediaMTX executable is included in the
downloadable application source. Its Basic-auth parser rejects a colon within
the decoded password, so the separate protocol receiver checks that case without
misrepresenting MediaMTX as a compatible camera.

Integration-test development found a source-readiness race and a Qt test-wait
that could starve the capture thread. The fixture now waits for actual SDP, and
the test wait yields to Python threads. Both affected integration checks passed
after those corrections. Review also caught URL-status misclassification and
non-BMP TOML serialization; both were corrected and regression-tested.

## Executed on target hardware

**None by this implementation.** Windows 11, a physical monitor and the user's
actual camera/NVR are not available in this cloud instance.

## Mandatory master-specification cases

| Case | Status |
|---|---|
| Known-good RTSP camera TCP, fullscreen | **Requires target hardware.** Local generated RTSP and offscreen rendering passed. |
| Real camera password containing `@ # % :` | **Requires target hardware.** Exact on-wire password bytes verified locally; no successful colon-password NVR/video login claimed. |
| Wrong password/channel/IP | Fixed classifications and auth limit tested; wrong real camera/password/path/IP **requires target hardware**. |
| 60-second cable unplug and automatic return | **Requires target hardware.** Local publisher-stop/recovery passed. |
| TV presets at 1366×768 / 1080p / 1440p | **Not implemented; Phase B**, then requires physical display checks. |
| CRT effects/reduce-motion safety | Static freeze passed; CRT effects **not implemented; Phase B**. |
| 1/2/4 moving faces at 1–3 m and ±30° | **Not implemented; Phases C/D; requires target hardware**. |
| Low light / IR | **Not executed; requires target hardware**, relevant to later detector phases. |
| Poster/photo detection behavior | **Not implemented; Phase C**. |
| Filter rotation modes | **Not implemented; Phase D**. |
| Hotkeys/PIN | Phase A subset tested offscreen; Windows confirmation required. Full table/admin console **Phase E**. |
| 24-hour soak / memory / CPU / FPS | **Not executed; requires target hardware**, with hardening in Phase F. |
| Privacy | Architecture and redaction tested; full target-machine filesystem/network audit **not executed**. |

No camera-to-screen latency, Windows install success, 25 FPS at 1080p,
face accuracy, CPU usage target, GLSL/CPU parity or 24-hour stability is claimed.
There are no YuNet models, fonts, bezels or masks bundled yet.

## Next required action

On the Windows target, install/configure this release and run the acceptance
checklist in [README.md](../README.md#acceptance-on-your-windows-pc--required-before-phase-b).
Report actual fullscreen, hotkey, power and 60-second cable-loss/recovery outcomes.
Continue to Phase B only after Phase A passes there.
