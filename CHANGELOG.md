# Release notes

## 0.2.0 — Editable connection window and ordinary exit

- Start in a normal window with RTSP URL, username, masked password and transport
  fields. Connect and Disconnect work without editing TOML or running terminal setup.
- Accept a full credentialed RTSP URL, extract credentials into separate fields,
  and save only the password-free URL. Passwords can remain session-only;
  remembering one in Windows Credential Manager is optional.
- Enter full screen through its button or F11. Esc returns to the connection
  window. Alt+Tab remains available; Close, Alt+F4 or Ctrl+Alt+Q exits without a
  PIN, including on connection errors.
- Remove automatic connection, always-on-top behavior and mandatory PIN startup.
  Keep errors visible beside editable controls and retire/switch capture workers
  in the background.
- Return to editable controls automatically on a fullscreen connection error;
  keep a visible Exit fullscreen button and provide an optional stop script.
- Installation opens the connection window; start and configure scripts use the
  same GUI. Existing configuration can be reused without its old PIN.

These changes follow the operator's updated requirements and replace the
original locked-kiosk entry/exit rules. This is still Phase A: CRT, TV frames and
face effects await target-PC acceptance. See [the test report](docs/TEST_REPORT.md)
for executed checks and remaining Windows verification.

## 0.1.0 — Original Phase A implementation

- Real PyAV RTSP TCP/UDP capture with bounded timeouts, latest-frame handoff,
  exponential reconnection and a pause after repeated explicit auth failures.
- Original borderless always-on-top fullscreen display with NO SIGNAL / CHANNEL
  ERROR states, hidden cursor, force reconnect and PIN-protected exit.
- Windows sleep prevention, local Credential Manager setup and sanitized logs.
- Windows install/start/probe/optional sign-in startup scripts, automated tests
  and a local MediaMTX/FFmpeg integration source.

The operator reported a fullscreen error display that was difficult to exit.
Version 0.2.0 replaces that interaction. Historical 0.1.0 cloud tests do not
validate the new window or establish target-PC acceptance.
