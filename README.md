# Haunted TV · 0.2.0 · Phase A

A Windows 11 RTSP viewer built with Python, PyAV and PySide6. It starts in a
**normal window with editable connection fields**. Enter your camera details,
click **Connect**, and choose full screen when you want it. You can switch to
other apps and close Haunted TV normally, including while a connection fails.

This release covers live streaming and recovery. TV bezels, CRT effects and
face filters remain later phases. The operator's latest request replaces the
locked-kiosk startup and exit rules in the
[original specification](docs/MASTER_PROMPT.md). No PIN is required.
See the [test report](docs/TEST_REPORT.md) for actual verification and limits.

## Windows quick start

1. Install **64-bit Python 3.12**, including the Python launcher, from python.org.
   The pinned dependencies support Python 3.10–3.13; later versions need revalidation.
2. Extract the current source ZIP into a writable folder, such as
   `Documents\HauntedTV`. Do not run scripts from inside the ZIP.
3. Double-click **`scripts\install.bat`**. It installs dependencies and opens
   the connection window. Installation needs Internet access; viewing your camera
   makes no cloud calls.
4. Enter your known-good RTSP URL, username and password. You can also paste a
   full URL containing credentials: the app separates them, moves the password
   into the masked field, and saves only the password-free URL. Use an H.264
   substream and **TCP** initially.
5. Click **Connect**. If it fails, read the status beside the connection controls,
   correct the fields and try again. The controls remain available.

For later launches, double-click **`scripts\start.bat`**. It opens the normal
connection window without connecting automatically. **`scripts\configure.bat`**
opens that same window; no terminal setup or manual TOML editing is needed.

### Updating from 0.1.0

Close the old process, download the current source ZIP, and extract it into a
fresh folder. Run the new **`scripts\install.bat`**, then use **Connect** in the
window. An old PIN is never required. You can reuse an existing
`config\haunted_tv.toml`, but it is simpler to enter the camera details in the
new window. Remembered passwords belong to your Windows account and the same
camera URL; re-enter one if it is unavailable.

If the old fullscreen process is still running, use Windows Task Manager to end
that Haunted TV process before launching the update.

## Connection and display controls

| Control | Action |
|---|---|
| **Connect** | Use the current URL, username, password and transport |
| **Disconnect** | Stop the connection and clear the live image |
| **Full screen**, `F11` | Toggle the video-only fullscreen view |
| `Esc` in full screen | Return to the normal window and connection controls |
| `F5` | Request a reconnect for the current connection |
| **Exit**, title-bar **Close**, `Alt+F4`, `Ctrl+Alt+Q` | Close without a PIN |
| `Alt+Tab` | Switch to other applications normally |

The window is not always on top. Full screen starts only when requested.
Connection errors never lock the controls or prevent closing. Switching or
stopping a stream happens in the background; the previous image is hidden
immediately. A decoder can take its configured network timeout to finish
shutting down.

A connection error during fullscreen returns to the editable window automatically.
The fullscreen view also keeps an **Exit fullscreen · Esc** button visible.
If an old process is stuck, `scripts\stop.bat` can stop the Haunted TV process
launched from that same folder without closing unrelated Python applications.

Camera passwords work for the current session without being saved. **Remember
password** optionally stores one in **Windows Credential Manager**. If the vault
is unavailable, the entered password can still be used for the connection;
check the warning and enter it again on the next launch. No plaintext password
is written to TOML. Never share a credentialed URL in screenshots, logs or chat.

## Configuration and streaming behavior

`config/haunted_tv.toml` is created on first run and ignored by Git. The window
saves connection settings with the password removed. Malformed settings fall
back to defaults with sanitized log messages. Existing `security.admin_pin_hash`
values are legacy settings and do not restrict startup or exit.

| Section/key | Default | Meaning |
|---|---|---|
| `stream.url` | empty | Password-free camera URL; no automatic startup connection |
| `stream.transport` | `tcp` | `tcp` or `udp` |
| `stream.connect_timeout_s` | `10` | Connection/open timeout budget |
| `stream.read_timeout_s` | `8` | Blocking-read and decoded-frame stall budget |
| `stream.reconnect_max_backoff_s` | `30` | Retry delays grow from 1 second up to this limit |
| `stream.max_auth_failures` | `3` | Pause after this many explicit authentication failures |
| `display.monitor` | `0` | Legacy setting; the viewer now uses its window's screen (drag it to the desired monitor) |
| `display.fps_cap` | `60` | GUI refresh cap; not a promise of 60 decoded FPS |
| `display.reduce_motion` | `false` | Retained for later effects; this release has static connection messages |

Live video keeps its aspect ratio with black letterboxing. Capture runs on a
worker, uses only the newest frame and drops old frames. There is no camera audio
playback. A quiet connection message replaces signal-loss static and error colour
bars. The normal window shows the specific safe error reason alongside editable
fields. The app never substitutes generated video for the camera.

Known authentication errors pause retries after the configured limit. Correct
credentials before clicking Connect or requesting another reconnect. Some
cameras return generic errors or timeouts for rejected logins; follow your NVR's
lockout policy. RTSPS is outside this release's supported workflow; keep TLS
verification enabled if investigating encrypted sources.

Optional sign-in startup is enabled only by running
`scripts\autostart_enable.bat` and removed with
`scripts\autostart_disable.bat`. It opens the normal window; it does not bypass
Connect or enable locked-kiosk behavior. Keep the application folder in place.

## Troubleshooting

| Symptom | Action |
|---|---|
| Error or no live video | Read the status, edit URL/account/transport, then Connect; Esc leaves full screen |
| Incorrect camera path | Use the exact path that works in your existing player; check the channel/substream |
| Authentication failed | Re-enter username/password, then Connect; respect the camera's lockout policy |
| Cannot remember password | Leave Remember password off; connect with the entered password and check the vault separately |
| Need another application | Use Alt+Tab; the viewer does not force itself back on top |
| Need to exit | Use Close, Alt+F4 or Ctrl+Alt+Q; no PIN is required |
| High delay | Try an H.264 substream, wired LAN and TCP; check NVR buffering |
| No window after launch | Read `%LOCALAPPDATA%\HauntedTV\logs\haunted_tv.log`; run `.venv\Scripts\python.exe main.py` from the application folder for startup errors |

For a separate check, run **`scripts\probe.bat`** with the viewer disconnected.
It checks DNS, TCP, unauthenticated OPTIONS/DESCRIBE and actual media decoding.
A decoded RGB frame is required for success; an open port alone does not pass.
Authenticated SDP/SETUP/media success is inferred together from that frame.
Ping is not used as proof of camera availability.

The probe and benchmark load saved settings and, for an authenticated stream,
its remembered vault password. They cannot access a password used only in the
window's current session. A failed probe in that situation does not show that
session-only login is broken. Neither tool displays or saves frames.

Logs rotate at 2 MiB each, keeping the current file and four backups. URLs,
registered passwords and exception text are sanitized; native FFmpeg logs are
suppressed. Do not share raw camera/server logs.

## Windows acceptance — required before Phase B

1. Launch the update. Confirm a normal editable window appears and no connection
   starts until Connect. Use the source that works in your existing Python player
   and check that the moving live image appears.
2. Enter an incorrect password or channel safely. Confirm the error is readable,
   fields remain editable, corrected Connect works, and Disconnect clears video.
   Check an actual password with special characters if applicable.
3. Enter full screen using the button or F11. Confirm Esc returns to the form,
   Alt+Tab reaches other apps, and Close/Alt+F4 works while disconnected,
   connecting and showing an error. No PIN or PC shutdown should be needed.
4. Unplug the camera network cable for **60 seconds** while connected. Confirm
   signal loss, then automatic return to a **live moving image** after reconnection.
5. Check the intended monitor and Windows display-sleep behavior. Confirm camera
   passwords are absent from saved TOML and application logs.

Report outcomes and sanitized errors. Cloud offscreen and local RTSP tests do
not verify the physical Windows window manager, camera/NVR or cable-loss recovery.
An existing working player establishes a good source; this updated application
still needs target-PC acceptance before Phase B.

## Development and local RTSP tests

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe; Linux: .venv/bin/python
.venv/bin/python -m pip install --only-binary=:all: -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

`QT_QPA_PLATFORM=offscreen` is for headless Linux tests, not normal Windows use.
Tests use generated data and local sockets. The application has no simulation
mode. Use the existing checkout in an isolated cloud task; no Git worktree is needed.

For genuine RTSP integration, install FFmpeg with `libx264` and official
[MediaMTX v1.12.3](https://github.com/bluenviron/mediamtx/releases/tag/v1.12.3).
Verify its archive against the release's `.sha256sum` before extracting.
No MediaMTX binary is included in this source.

```sh
HAUNTED_TV_MEDIAMTX=/path/to/mediamtx .venv/bin/python -m pytest -q tests/test_rtsp_integration.py
# Optional manual source, loopback only:
.venv/bin/python tools/local_rtsp.py --mediamtx /path/to/mediamtx
```

In PowerShell set `$env:HAUNTED_TV_MEDIAMTX='C:\path\mediamtx.exe'`, then run
`.venv\Scripts\python.exe -m pytest -q tests\test_rtsp_integration.py`.
The fixture starts/stops its own FFmpeg publisher, checks decoded RGB frames and
recovery, and cleans up subprocesses. Without MediaMTX/FFmpeg these tests are
explicitly skipped. Set `HAUNTED_TV_NETWORK_TESTS=1` for additional loopback tests
of actual PyAV Basic authentication and rejected-login retry limits. Socket
access is required. These are developer sources, never production fallback video.

For capture throughput on your PC, run
`.venv\Scripts\python.exe -m tools.benchmark --seconds 60` with the viewer
disconnected and credentials remembered if needed. This measures decoded-frame
throughput and frame gaps, not rendering FPS or camera-to-screen latency.

## Privacy and safe use

Video is processed in memory and discarded. There is no recognition, face
database, recording, snapshot saving, upload, telemetry or camera audio playback.
The app contacts only the configured camera host. Dependency installation and
optional developer tools separately use their package/release hosts.

Use cameras you own, aimed at your own premises. Avoid neighbours/public spaces.
Consider a sign: **“Live display — not recorded.”** Check local privacy rules,
including the Philippine Data Privacy Act and applicable barangay/building rules,
particularly where visitors and children may appear. Connection messages are
static with no strobe or flashing graphics. Later effects must retain the
specified photosensitivity safeguards.

## Roadmap and limits

Phase A target acceptance is pending. Phase B adds procedural bezels, CRT GLSL
and CPU fallback; Phase C adds licensed YuNet detection and stable tracking;
Phase D adds original face effects and quality adaptation. Later configuration
and packaging work must retain the easy entry and exit requested for 0.2.0.
Phase F includes fresh-Windows validation and a 24-hour soak test.

No 25 FPS, under-300 ms camera latency, Windows-install success, detection accuracy
or 24-hour stability claim is made. There are no bezel/font/model assets yet.
See [third-party notices](THIRD_PARTY.md) and [release notes](CHANGELOG.md).
