# Phase A test report — 0.2.0 — 2026-10-28

## Scope and operator feedback

Version 0.2.0 follows the operator's updated workflow: start in a normal editable
connection window, connect explicitly, enter full screen optionally, and leave
or close normally without a PIN or always-on-top restriction. Those instructions
replace the corresponding locked-kiosk rules in the original master prompt.
CRT, bezels and face effects remain later phases.

The operator reports that their camera works with an existing Python player.
They also reported that the previous Haunted TV build showed colour bars and
was difficult to exit, leading to a PC shutdown. That is a reported target-PC
failure of the previous interaction, not a passing acceptance result. The revised
0.2.0 workflow must be checked on the actual Windows PC.

## Current 0.2.0 verification

**110 passed, 0 failed, 0 skipped in 29.40 seconds** with both network-test
variables enabled. This is runner time, not a video performance measurement.
Validation ran on Linux x86-64, CPython 3.12.14, Qt/PySide6 6.9.1 offscreen,
PyAV 16.0.1 and NumPy 2.2.6. `pip check` and Python byte-compilation also passed.
No Windows 11 or real camera success is claimed.

Current executed checks:

| Check | Passing evidence and limits |
|---|---|
| Normal startup | Visible connection fields; no PIN gate, fullscreen, always-on-top flag or automatic connection |
| Credentialed URL import | Password extracted into masked field; saved URL contains no password; special characters decoded once |
| Connect/Disconnect | Current settings/session credentials reach capture; disconnect hides old frames and retires capture in the background |
| Connection errors | Safe reason shown; fields stay editable; corrected connection can be requested |
| Optional password storage | Session-only login works without the vault; vault failure warns but does not block a supplied password |
| Fullscreen controls | Button/F11 enters video-only view; Esc returns to connection controls |
| Ordinary exit | Close and shortcut paths require no PIN, including during connection or errors |
| Stream switching | Retire old worker before starting latest request; no stale image or unbounded workers |
| Real RTSP | Local MediaMTX/FFmpeg decode, publisher loss/recovery and media-to-widget rendering |
| Privacy | No credentialed URL/password written to TOML or logs; no production frames saved |

The real MediaMTX/FFmpeg GUI test clicked Connect in the new form, displayed
actual decoded H.264 video, entered fullscreen, stopped the publisher and verified
automatic return to editable controls, restarted the publisher and verified live
recovery, then disconnected and closed the session. All owned capture threads
finished within the test deadline. The fixture uses generated video on loopback,
not the operator's NVR or physical network cable.

Regression tests also cover explicit empty pasted passwords, masking credentials
even with a malformed port, optional-vault failure without blocking a supplied
password, safe stream replacement and startup/exit without a configured PIN.

Offscreen Qt tests verify program behavior and flags. Physical Alt+Tab, Alt+F4,
monitor selection, visible rendering and Windows Credential Manager need target-PC
verification even if automated checks pass.

## Historical 0.1.0 cloud evidence

The prior release report recorded **76 passed, 0 failed, 0 skipped in 22.88
seconds** for 0.1.0. This is historical runner time, not video performance, and
does not establish 0.2.0 readiness. Its kiosk/PIN assertions describe behavior
deliberately removed in 0.2.0.

That run used Linux x86-64, CPython 3.12.14, PySide6/Qt 6.9.1 offscreen,
PyAV 16.0.1 and NumPy 2.2.6. Integration used system FFmpeg 7.1.5 with libx264
and MediaMTX 1.12.3 on loopback. No real camera credentials were used.
`pip check`, CLI entry-point checks and Python byte-compilation were also
reported as passed for 0.1.0.

Historical evidence included:

- Real generated H.264 RTSP video decoded into advancing nonuniform RGB frames,
  publisher-stop recovery, bounded capture shutdown and offscreen rendering.
- A local probe and capture-throughput run. Authenticated SDP/SETUP/media were
  inferred together from decoded video, not independently timed.
- Actual PyAV Basic-auth handshakes checking exact special-character password
  bytes and the rejected-login retry limit. The test receiver returned an error
  after checking credentials; it did not establish a successful camera login.
- Config validation, PIN hashing, mocked vault failures, log redaction/rotation,
  frozen static and mocked Windows sleep API calls.

The MediaMTX archive was verified against its official SHA-256 file:
`450d1172bf6708cbd630eada115ccfc33453227e16750369113d1dfe34f876d8`
for `mediamtx_v1.12.3_linux_amd64.tar.gz`. No MediaMTX executable is included
in the source archive. Its Basic-auth parser rejected a colon within the decoded
password; a separate protocol receiver covered that case without claiming
MediaMTX/camera compatibility.

## Reproducing automated checks

Run from the checkout on Linux with permission to use loopback sockets:

```sh
QT_QPA_PLATFORM=offscreen \
HAUNTED_TV_NETWORK_TESTS=1 \
HAUNTED_TV_MEDIAMTX=/workspace/haunted-tv-tools/mediamtx \
.venv/bin/python -m pytest -q
```

Use a locally installed, checksum-verified MediaMTX binary. Without MediaMTX,
FFmpeg and the opt-in variables, real network/media tests are skipped. Record
passed, failed and skipped counts separately. A default run with skipped media
tests is not real RTSP validation. See the README for Windows/manual-source steps.

## Target-PC acceptance — not yet verified for 0.2.0

| Case | Current status |
|---|---|
| Fresh Windows install and first launch | **Requires target hardware.** Confirm form opens without auto-connect. |
| Known-good camera TCP | **Requires target hardware.** Existing player success is source evidence only. |
| Credentialed URL import and special-character camera password | **Requires target hardware.** Confirm live login and password-free TOML/logs. |
| Wrong password/channel/IP | **Requires target hardware.** Error stays readable/editable and app stays closeable. |
| Corrected credentials and repeat Connect/Disconnect | **Requires target hardware.** Confirm clean switching and responsive controls. |
| Full screen, F11 and Esc | **Requires target hardware.** Esc must return to connection fields. |
| Alt+Tab, Close, Alt+F4 and Ctrl+Alt+Q | **Requires target hardware.** No PIN, forced focus or PC shutdown required. |
| Optional Credential Manager remember | **Requires target hardware.** Session password must work if remembering fails. |
| 60-second cable loss and recovery | **Requires target hardware.** Publisher-stop tests do not replace it. |
| Monitor selection and display sleep restoration | **Requires target hardware.** Mocked Windows API checks are insufficient. |
| Target filesystem/network privacy audit | **Not executed.** Production video is designed to stay in memory. |
| 24-hour soak and memory/CPU/FPS targets | **Not executed; requires target hardware**, with hardening in Phase F. |
| TV presets, CRT/parity and resolution scaling | **Not implemented; Phase B.** |
| Face accuracy, tracking, low-light/IR and photo/poster behavior | **Not implemented; Phase C; requires target hardware.** |
| Moving/tilted faces, effects and rotation | **Not implemented; Phases C/D; requires target hardware.** |

No camera-to-screen latency, successful Windows install, 25 FPS at 1080p,
face accuracy, CPU target, shader/CPU parity or 24-hour stability is claimed.
No YuNet model, font, bezel or mask assets are bundled yet.

## Next required action

On the Windows target, run the updated
[Windows acceptance checklist](../README.md#windows-acceptance--required-before-phase-b).
Report actual connection, error editing, easy exit, fullscreen return and
60-second cable-loss outcomes. Phase B remains gated on successful Phase A
acceptance using this revised workflow.
