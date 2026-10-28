# Haunted TV · 0.1.0 · Phase A

A local-only Windows 11 RTSP kiosk, built with Python, PyAV and PySide6.
**This release implements Phase A, not the finished Halloween display.** The
master specification requires a successful target-PC test before each next
phase. TV bezels, CRT shaders, face detection, filters and the admin console
are intentionally pending that gate. See [the original requirements](docs/MASTER_PROMPT.md)
and [the test report](docs/TEST_REPORT.md).

## Windows quick start

1. Install **64-bit Python 3.12** (recommended), with the Python launcher, from python.org.
   This pinned release supports Python 3.10–3.13; future Python versions need revalidation.
2. Extract the source into a writable folder, such as `Documents\HauntedTV`.
3. Double-click **`scripts\install.bat`**. Internet access is needed to install
   dependencies; normal operation makes no cloud calls. Setup time depends on downloads.
4. Setup asks for your known-good RTSP URL **without a password**, for example
   `rtsp://viewer@192.168.1.50:554/Streaming/Channels/202`. Enter the camera
   password at the separate hidden prompt. It goes to **Windows Credential Manager**,
   never into TOML. Choose TCP, a monitor index (first screen is `0`), and a
   **6–12 digit operator PIN**. Use an H.264 substream initially.
5. Double-click **`scripts\start.bat`**. There are no visible controls.

Use `scripts\configure.bat` later to change settings while the kiosk is stopped.
Camera credentials are scoped to your Windows user and the configured URL.
Changing host, username or channel requires entering its password again. Do not
place credentials in filenames, command arguments, screenshots, or chat.

## Phase A controls

| Hotkey | Action |
|---|---|
| `F5` | Force reconnect, including resetting the authentication retry limit |
| `Ctrl+Alt+Q` | Open hidden PIN entry; Enter confirms, Esc cancels |
| `Esc`, `Alt+F4` | Do not quit the kiosk |

The cursor stays hidden during display and appears over the hidden PIN panel.
Three incorrect PIN attempts delay further attempts for 30 seconds. This is a
decoration kiosk, **not an OS security boundary**; Task Manager, Windows session
controls and physical access can still end it. Keep the PIN available to the operator.

`Ctrl+Alt+H`, F1–F4 and F8 are **not implemented in Phase A**. No nonfunctional
buttons or filter controls are displayed. Optional sign-in startup is enabled
only by running `scripts\autostart_enable.bat`; remove it with
`scripts\autostart_disable.bat`. Keep the extracted application in place afterward.

## Configuration

`config/haunted_tv.toml` is created on first run and ignored by Git. The setup
script updates it atomically. Defaults below describe Phase A only:

| Section/key | Default | Meaning |
|---|---|---|
| `stream.url` | empty | Password-free `rtsp://` camera URL; empty shows NO SIGNAL |
| `stream.transport` | `tcp` | `tcp` or `udp` |
| `stream.connect_timeout_s` | `10` | Interrupt budget for connection/open |
| `stream.read_timeout_s` | `8` | Blocking-read and decoded-frame stall budget |
| `stream.reconnect_max_backoff_s` | `30` | Exponential retries: 1, 2, 4… up to this limit |
| `stream.max_auth_failures` | `3` | Pause after this many explicit authentication failures |
| `display.monitor` | `0` | Monitor index; unavailable index falls back to last available screen |
| `display.fps_cap` | `60` | GUI refresh cap; does not promise 60 decoded FPS |
| `display.reduce_motion` | `false` | Freeze signal-loss static; no flicker or strobe effects implemented |
| `security.admin_pin_hash` | empty | Salted PBKDF2-SHA256; set by setup, required to launch |

Malformed settings fall back to safe defaults with sanitized log messages.
An invalid or missing PIN prevents kiosk launch until configured. Never put
passwords or access tokens in the URL. URL userinfo and query strings are removed
from logs. RTSPS support is outside Phase A; do not disable TLS verification to
connect to an encrypted source.

Video uses aspect-preserving fit with black letterboxing, a single latest-frame
slot and no growing frame queue. Capture and PIN hashing run off the GUI thread.
There is no camera audio playback. Stream interruption displays low-amplitude
static and NO SIGNAL; known authentication/path/decoder errors display colour
bars and CHANNEL ERROR. Logs hold the reason. Startup remains NO SIGNAL until
real video arrives: the app never substitutes a test pattern for the camera.

Known authentication failures pause retries after three attempts. F5 resets the
limit only after you correct credentials. Some cameras return timeouts or generic
errors rather than explicit authentication errors; observe the camera's lockout
policy and use the diagnostic probe once instead of repeatedly retrying passwords.

## Troubleshooting

Run **`scripts\probe.bat`** with the kiosk stopped. It checks DNS, TCP,
unauthenticated OPTIONS/DESCRIBE, and actual media decoding using the configured
credentials. A decoded RGB frame is required for success. For authenticated cameras,
SDP/SETUP/media success is inferred together from that frame; the tool does not
pretend to independently measure each authenticated stage. Ping is never used as
proof that a camera is offline. The probe does not display or save a frame.

| Symptom | Action |
|---|---|
| No window after starting | Check `%LOCALAPPDATA%\HauntedTV\logs\haunted_tv.log`; run `.venv\Scripts\python.exe main.py` from the app folder for dependency/startup errors |
| NO SIGNAL | Configure a URL; check camera power, route, TCP port, transport and firewall; run probe |
| CHANNEL ERROR | Check sanitized log state; correct camera account or channel using configure, then restart/F5 |
| Wrong screen | Stop, change `display.monitor`, restart |
| High delay | Use H.264 substream, wired LAN and TCP initially; remove NVR buffering if supported |
| Cannot store password | Run under your normal Windows account; check Credential Manager availability; insecure file stores are not used |
| Locked out of quit | Use your PIN; after three failures wait 30 s. For recovery stop via Task Manager and run configure |

Logs rotate at 2 MiB each, retaining the current file plus four backups. Do not
share raw camera/server logs; app logs sanitize URLs, registered secrets and
exception text. Camera/native FFmpeg logs are suppressed to avoid leaking URLs.

## Acceptance on your Windows PC — required before Phase B

1. Use the same URL that works in your existing Python player. Confirm video
   fills the selected screen with correct letterboxing, no borders/controls and
   a hidden cursor. Confirm F5 and the PIN-protected quit.
2. Unplug the camera network cable for **60 seconds**. Verify NO SIGNAL appears;
   reconnect it and verify the **live moving image returns without interaction**.
3. Check a wrong password and channel safely, respecting NVR lockout policy.
   Check your special-character password (`@ # % :`) using the hidden prompt.
   Confirm the password never appears in app logs or TOML.
4. Confirm Windows does not turn off the display while running and normal power
   behavior returns after quitting. Check the intended monitor(s).

Report results and sanitized errors. These checks, actual Windows installation,
and physical display behavior have **not** been executed in the cloud. A working
camera in another player establishes a good source, but does not pass this app's
Phase A acceptance. Phase B begins after the checks above pass on the target PC.

## Development and genuine local RTSP test

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe; Linux: .venv/bin/python
.venv/bin/python -m pip install --only-binary=:all: -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

On a headless Linux machine set `QT_QPA_PLATFORM=offscreen` for UI tests. Tests
use generated data and local sockets; the production app has no simulation mode.
No Git worktree is needed: use the task's existing isolated checkout.

For real RTSP integration, install FFmpeg with `libx264` and the official
[MediaMTX v1.12.3](https://github.com/bluenviron/mediamtx/releases/tag/v1.12.3)
binary for your OS. Verify the archive against the release's `.sha256sum` file
before extracting. No MediaMTX binary is redistributed in this source archive.

```sh
HAUNTED_TV_MEDIAMTX=/path/to/mediamtx .venv/bin/python -m pytest -q tests/test_rtsp_integration.py
# Optional manual source in a second terminal (loopback only):
.venv/bin/python tools/local_rtsp.py --mediamtx /path/to/mediamtx
```

In PowerShell use `$env:HAUNTED_TV_MEDIAMTX='C:\path\mediamtx.exe'` and run
`.venv\Scripts\python.exe -m pytest -q tests\test_rtsp_integration.py`.
The integration test starts and stops its own FFmpeg publisher, verifies decoded
RGB frames and reconnection, and cleans up its subprocesses. Without the binary
and FFmpeg it is explicitly skipped. Socket access is required.

For a capture-throughput measurement on your PC, run
`.venv\Scripts\python.exe -m tools.benchmark --seconds 60` with the kiosk stopped.
It reports actual decoded-frame throughput and frame gaps, without saving video.
It does not measure rendering FPS or camera-to-screen latency.

Two further opt-in protocol tests use the actual PyAV/FFmpeg client against a
loopback Basic-auth receiver: set `HAUNTED_TV_NETWORK_TESTS=1` to run them. They
check exact special-character password transmission and a three-attempt auth
limit. The receiver deliberately supplies no video, so they do not prove camera
compatibility. Set both test variables to run the entire suite without skips.

## Privacy and safe use

Detection is planned; this release does not implement recognition, embeddings,
face databases, recording, snapshots, uploads or telemetry. Video remains in
memory and is discarded. Application networking contacts only the configured
camera host; dependency installation and optional developer tooling separately
use their package/release hosts. No camera audio is played. Passwords are never
stored in plaintext configuration.

Use only cameras you own, aimed at your own premises. Avoid capturing neighbours
or public spaces. Consider a sign: **“Live display — not recorded.”** Check local
privacy requirements, including the Philippine Data Privacy Act and applicable
barangay/building rules, particularly where visitors and children may appear.
Signal-loss static has a narrow, stable luminance range; use `reduce_motion=true`
to freeze it. Later effects must retain the mandatory photosensitivity safeguards.

## Roadmap and limits

Phase A is implemented and cloud-tested; **target acceptance is pending**.
Phase B: procedural bezels, CRT GLSL and CPU fallback. Phase C: licensed YuNet
detector and stable tracking. Phase D: original procedural face effects and
quality adaptation. Phase E: hidden admin console and complete configurable
hotkeys. Phase F: packaging, fresh-Windows verification and a 24-hour soak test.

No 25 FPS, under-300 ms camera latency, Windows readiness, face-detection accuracy
or unattended 24-hour claim is made by this release. There are no bezel/font/model
assets yet. See [third-party notices](THIRD_PARTY.md) and [release notes](CHANGELOG.md).
