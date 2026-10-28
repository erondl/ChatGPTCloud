# MASTER DEVELOPMENT PROMPT

## "Haunted TV" – Halloween CCTV Display with Old-Monitor Frame and Live Face Filters

**Project type:** Kiosk-style desktop application (decoration / entertainment display)
**Platform:** Windows 11, 64-bit
**Language:** Python 3.10+ (64-bit)
**GUI / rendering:** PySide6 (Qt 6) with `QOpenGLWidget` (GLSL shaders), CPU fallback path
**Video input:** RTSP (IP camera or NVR channel) via PyAV (FFmpeg); LibVLC is NOT used for this display (see 2)
**Computer vision:** OpenCV (YuNet face detector + 5-point landmarks), optional MediaPipe Face Landmarker, NumPy
**Architecture:** Modular, offline-first, multi-threaded, runs unattended for days

---

## 0. HOW TO USE THIS PROMPT

Paste it into an AI coding assistant as one task. If the "CCTV VMS – Phase 1 RTSP Test Player" project already exists, reuse its `streaming/rtsp_validator.py`, `streaming/stream_diagnostics.py`, `streaming/base_player.py` and `streaming/ffmpeg_player.py` instead of rewriting them. Follow the phases in section 12 in order; do not start a phase until the previous one passes its acceptance criteria on the target PC.

---

## 1. PRIMARY OBJECTIVE

Act as a Senior Python Engineer, Real-Time Computer Vision Developer, Qt/OpenGL Graphics Programmer and Video Streaming Specialist.

Build a full-screen application that:

1. Plays a live RTSP stream from a CCTV camera or NVR channel.
2. Presents it inside a convincing **old TV / vintage CRT monitor** frame with authentic CRT screen effects.
3. **Hides every option, button and setting** while running (kiosk mode); control is only through hidden hotkeys and a config file.
4. **Detects human faces in the live stream and transforms them in real time** with Halloween filters (zombie, skeleton, pumpkin head, ghost, vampire, demon eyes, accessories, glitch).
5. Runs unattended all night, recovers from network loss by itself, and never needs a keyboard or mouse once started.

The result is a Halloween decoration: a "haunted television" showing the front porch, where visitors see themselves turned into monsters.

Critical requirement: it must genuinely work on the supplied stream. No simulated video, no placeholder effects, no buttons without function. If something cannot be tested in the development environment, say so explicitly instead of claiming success.

---

## 2. KEY ARCHITECTURE DECISION: OWN FRAME PIPELINE (NOT EMBEDDED VLC)

LibVLC embedded through a native window handle draws into its own child window, so shaders, overlays and face filters cannot be applied to it. Therefore:

- Decode with **PyAV** (FFmpeg): RTSP over TCP by default, UDP optional, configurable timeouts, reconnect with bounded exponential backoff.
- Convert frames to RGB `numpy` arrays; hand them to the render thread as textures.
- Render the final image (CRT shader + bezel + OSD) in one `QOpenGLWidget` at the screen's refresh rate, independent of the camera frame rate.
- Keep an optional plain "LibVLC view" only as a diagnostic/fallback mode, with no effects.

Threads (never block the GUI thread):

| Thread | Job |
|---|---|
| Capture | RTSP connect, demux, decode, latest-frame slot (drop old frames, never queue) |
| Inference | Face detection/tracking on a downscaled copy at a limited rate |
| Render (GUI) | Upload texture, run shaders, draw bezel, OSD, overlays |
| Watchdog | Detect stalled stream, restart capture, prevent system sleep |

Frame hand-off uses a lock-protected "latest frame" slot. Latency target: under 300 ms camera-to-screen on a LAN.

---

## 3. HARDWARE / PERFORMANCE TARGETS

- Reference PC: mid-range laptop/desktop, Intel i5-class CPU, integrated GPU, no dedicated GPU required.
- Input: use the **substream** (e.g. 640x360 to 1280x720, H.264) when the NVR offers one; main stream optional.
- Output: 1920x1080 fullscreen at **at least 25 FPS** including CRT shader and face effects.
- Face detection runs on a frame downscaled to about 320 px width, every N-th frame (default N=3), with a tracker bridging the frames in between.
- CPU usage target: below 60% on the reference PC for one stream and up to 4 simultaneous faces.
- If FPS falls under 20, automatically lower effect quality in this order: bloom, chromatic aberration, noise resolution, detection rate, mesh warps. Log each automatic downgrade.

---

## 4. KIOSK MODE (HIDE ALL OPTIONS)

The default launch is a clean kiosk:

- Borderless, always-on-top, full screen on a chosen monitor (config: monitor index).
- Mouse cursor hidden (hide after 1 s of inactivity; reappears only in the hidden admin overlay).
- No title bar, menus, toolbars, status text, log panels or buttons on screen.
- Prevent Windows sleep/screen-off/screensaver while running (`SetThreadExecutionState`); restore on exit.
- Optional auto-start with Windows (Startup folder shortcut or Task Scheduler entry created by a script, never by default).
- Graceful on-screen states, drawn **inside the TV screen** as in-theme graphics, never as dialogs:
  - No signal / reconnecting: animated TV static with the text "NO SIGNAL" in a VHS font.
  - Authentication or path error: "CHANNEL ERROR" test pattern (colour bars). The detailed reason goes only to the log file.

### Hidden controls (all configurable)

| Hotkey | Action |
|---|---|
| `Ctrl+Alt+H` | Show/hide the **admin overlay** (PIN required, PIN stored hashed in config) |
| `F1` | Next face filter · `Shift+F1` previous · `F2` filters on/off |
| `F3` | Next TV preset · `F4` CRT effects on/off |
| `F5` | Force reconnect |
| `F8` | Toggle debug view (face boxes, landmarks, FPS) |
| `Ctrl+Alt+Q` (+ PIN) | Quit (plain `Esc` must NOT quit) |

The admin overlay (Qt translucent panel, hidden by default) provides: RTSP URL and transport, filter list and rotation timing, CRT intensity sliders, preset choice, monitor selection, "Test connection". Passwords are masked, never logged, stored using Windows Credential Manager (`keyring`) – not in plaintext config.

---

## 5. OLD-TV / OLD-MONITOR FRAME (BEZEL)

### 5.1 Presets (selectable, hot-swappable)

1. **Haunted 1950s Console TV** – wooden cabinet, rounded glass, two knobs, speaker grille, warm sepia-leaning phosphor.
2. **Cursed Security Monitor** – grey plastic 1990s CCTV monitor, small green power LED, "CAM 01" label, slightly green phosphor, red `REC` dot blinking (decorative only, must not imply recording).
3. **80s Computer Monitor** – beige case, curved glass, amber/green monochrome option.
4. **Broken Cathode Ray** – any preset with heavy damage: cracks overlay, dust, flicker, occasional channel-hop static.

### 5.2 Construction rules

- Each preset = a transparent PNG bezel (screen area is transparent, aspect ratio of the screen rectangle stored in a JSON sidecar with corner-radius and screen polygon) + optional layers (glass reflection, dust, cracks) + optional LED/knob animations.
- Supply **original, procedurally generated or CC0 assets**. Do not use copyrighted TV brands, logos or characters. Include a script `tools/make_bezels.py` that generates simple vector bezels with Pillow/QPainter so the app works without external art.
- The video is mapped into the screen polygon with correct aspect ratio: modes `fit` (letterbox inside the glass), `fill` (crop), `stretch`. Default `fit` with a 4:3 option that pillarboxes 16:9 video the way old TVs did.
- Bezel scales to the display while keeping aspect; the surrounding background is near-black with a soft room-light vignette.
- Resolution independent: 1366x768, 1920x1080, 2560x1440, 3840x2160.

### 5.3 On-screen display (OSD) inside the glass

Optional, configurable, in a pixel/VHS font (ship an OFL-licensed font):

- Timestamp `OCT 31 2026  21:47:03` (current system time, fake-VHS style), `CAM 01`, `REC` dot, tracking bar, channel number briefly when switching presets.

---

## 6. CRT SCREEN EFFECTS (GLSL FRAGMENT SHADER)

Implement as one multi-pass or single-pass shader with uniform parameters; each effect individually switchable, with `intensity` 0.0–1.0 and a documented default. Provide a numpy/OpenCV CPU fallback for machines without OpenGL 3.3.

| Effect | Description | Default |
|---|---|---|
| Barrel distortion | Curved glass, corners masked with rounded black | 0.12 |
| Scanlines | Horizontal dark lines locked to output rows, slight brightness wobble | 0.35 |
| Shadow mask / RGB phosphor | Subtle RGB triad pattern (only visible when output is large enough) | 0.15 |
| Chromatic aberration | R/B channel offset growing toward the edges | 0.25 |
| Bloom / glow | Cheap blur on highlights | 0.30 |
| Vignette | Darker corners | 0.35 |
| Film/analog noise | Animated per-frame grain | 0.12 |
| Colour bleed / smear | Horizontal chroma smear, VHS look | 0.20 |
| Brightness flicker | Slow ±3% mains flicker (see 6.1 safety) | 0.10 |
| Rolling bar | Slow vertical hum bar | 0.15 |
| Horizontal jitter / tracking glitch | Occasional line displacement bursts | 0.10 |
| Phosphor tint | Colour LUT: neutral, green, amber, sepia | per preset |
| Power-on / power-off | Spot-expand animation on start; collapse to a dot on exit | on |
| Channel-hop static | 0.3–0.6 s of noise when switching preset or filter | on |

### 6.1 Photosensitivity safety (mandatory)

No effect may flash more than **3 times per second**; full-screen luminance changes limited to modest amplitude; a config switch `reduce_motion=true` disables flicker, rolling bar, jitter, channel-hop flashing and jump scares at once.

---

## 7. LIVE FACE DETECTION AND HALLOWEEN TRANSFORMS

### 7.1 Detection and tracking

- Detector: OpenCV `FaceDetectorYN` with the **YuNet** ONNX model (bundle the model file; check its licence and record it in `THIRD_PARTY.md`). Fallback: MediaPipe Face Detection/Landmarker if installed. Pin library versions in `requirements.txt` and verify they install on the target Python version.
- Output per face: bounding box, confidence, 5 landmarks (eyes, nose tip, mouth corners); optional dense landmarks when MediaPipe is available.
- Stabilise: lightweight tracker (IoU + Kalman or exponential smoothing) with stable face IDs for the effect only; smooth landmarks (One-Euro filter) to avoid jitter; fade effects in/out over about 250 ms when a face appears/disappears.
- Config: `min_confidence` (0.6), `min_face_px` (48), `max_faces` (6), `detect_every_n_frames` (3), `detection_width` (320).
- Handle: multiple faces, small/distant faces, head tilt (roll computed from eye line), partial profile (fall back to box-based placement), glasses/hats, low light and IR/night mode (greyscale video: effects must still work; use colour-neutral tinting).

### 7.2 Effect library (each effect = a plugin class with `prepare()`, `apply(frame, faces)` and metadata)

| Filter | Method |
|---|---|
| **Zombie** | Green-grey skin tint limited to a soft face mask, dark eye sockets, scar/blood decals aligned by landmarks |
| **Skeleton** | Alpha-blended skull face-paint overlay warped by an affine transform from eyes+mouth landmarks; hollow nose, teeth line |
| **Jack-o'-lantern** | Pumpkin head overlay sized from the face box with a flicker glow inside the eyes/mouth, rotated by head roll |
| **Ghost** | Desaturate + white translucency + soft trailing echo of the previous 3–5 frames, slight upward drift |
| **Vampire** | Pale skin, red glowing eyes, fangs decal on mouth landmarks |
| **Demon eyes** | Glowing red/orange eye patches with bloom; optional horns above the head |
| **Accessories** | Witch hat, devil horns, spider-web corner — anchored above the box with roll and scale from landmarks |
| **Melt / bulge warp** | Mesh warp or bulge distortion on the face region (OpenCV `remap`) |
| **Glitch face** | Block displacement + RGB split limited to the face rectangle |

Rules:

- Overlays are PNG with alpha, in `assets/masks/<filter>/`; provide original CC0/own-drawn assets generated or drawn procedurally. **No copyrighted characters or film masks.**
- Alpha-composite in the shader (face quads textured with the decal) wherever possible; CPU path only as a fallback.
- Rotation modes: `fixed`, `sequential` and `random` change every N seconds, or assign a **different random filter per new face** (config).
- Filters stay off-frame safe: if detection fails for one frame, keep the previous overlay for up to 300 ms to avoid flicker.
- Optional "boo" mode: when a new face appears, a brief (≤ 0.5 s) scare effect (ghost pop, no strobe) with an optional local sound file. Default **off**; obeys `reduce_motion`.
- Optional ambient audio loop (local file) and optional sound on filter change; audio never comes from the camera.

---

## 8. PRIVACY, ETHICS AND LEGAL GUARDRAILS (MANDATORY)

- **Detection only. No face recognition or identification**: no embeddings, no face database, no names, no matching against anyone.
- No recording, no snapshots, no saving of frames or faces to disk, and no network upload by default; everything is processed in memory and discarded. Any future recording feature must be separate and explicit.
- No telemetry and no cloud calls; the app only contacts the RTSP host entered by the operator.
- Document in the README: use only cameras you own, aimed at your own premises; avoid capturing neighbours/public spaces; consider a visible sign such as "Live display — not recorded"; check local privacy rules (for example the Philippine Data Privacy Act and barangay/building rules) before pointing a camera at an area where visitors, including children, appear.
- Keep content family-friendly (no gore beyond cartoon level); photosensitivity safeguards from 6.1 stay enabled by default.
- Never log passwords or full credentialed URLs; sanitise logs and diagnostic exports.

---

## 9. CONFIGURATION

Single file `config/haunted_tv.toml` (created with defaults on first run) plus Credential Manager for the password.

```toml
[stream]
url = "rtsp://<user>@172.50.10.12:554/Streaming/Channels/202"   # password in Credential Manager
transport = "tcp"
connect_timeout_s = 10
read_timeout_s = 8
reconnect_max_backoff_s = 30

[display]
monitor = 0
preset = "cursed_security_monitor"
aspect_mode = "fit"        # fit | fill | stretch
fps_cap = 60
reduce_motion = false

[crt]
barrel = 0.12
scanlines = 0.35
chromatic = 0.25
bloom = 0.30
vignette = 0.35
noise = 0.12
tint = "green"

[faces]
enabled = true
filters = ["zombie", "skeleton", "jack_o_lantern", "ghost", "vampire"]
rotation = "per_face"      # fixed | sequential | per_face | timed
rotate_every_s = 20
detect_every_n_frames = 3
min_confidence = 0.6
max_faces = 6

[security]
admin_pin_hash = ""        # set from the admin overlay
```

Validate on load, report errors in the log and fall back to defaults; never crash on a bad value.

---

## 10. SOFTWARE ARCHITECTURE

```
haunted_tv/
├── main.py                    # kiosk entry point
├── requirements.txt           # pinned versions
├── README.md  THIRD_PARTY.md
├── config/                    # defaults, TOML loader/validator, credential store wrapper
├── core/                      # app controller, state machine, watchdog, power management
├── streaming/                 # rtsp_validator, stream_diagnostics, pyav_capture (reconnect/backoff)
├── vision/                    # face_detector (YuNet/MediaPipe), tracker, smoothing, landmarks
├── effects/                   # base_effect, zombie, skeleton, jack_o_lantern, ghost, vampire, demon, accessories, warp, glitch
├── render/                    # gl_widget, shaders/*.glsl, crt_pipeline, bezel_loader, osd, cpu_fallback
├── ui/                        # kiosk_window, admin_overlay (hidden), hotkeys
├── assets/                    # bezels/, masks/, fonts/, sounds/   (original or CC0 only)
├── tools/                     # make_bezels.py, make_masks.py, benchmark.py
├── scripts/                   # install.bat, start.bat, autostart_enable.bat, probe.bat
└── tests/
```

Separate concerns: no network or CV code inside UI classes; effects are pluggable; everything long-running lives off the GUI thread; resources (GL textures, ONNX sessions, FFmpeg containers) are released on exit.

---

## 11. ERROR HANDLING AND RELIABILITY

- Connection states: Disconnected, Connecting, Live, Reconnecting, Authentication Failed, Stream Unavailable, Network Error, Decoder Error. Each maps to an in-theme screen (section 4) and a precise log line.
- Reuse the staged diagnostic probe (DNS, TCP port, OPTIONS, DESCRIBE + authentication, SDP, SETUP, RTP data) so that failures are explained, not just shown as "offline". Ping must never be used as proof of offline.
- Never auto-retry after an authentication failure more than a few times (avoid locking the NVR account).
- Stall watchdog: no new frame for 8 s → restart capture; memory/handle growth check; restart the whole pipeline after 3 consecutive failures.
- Rotating log files in `%LOCALAPPDATA%\HauntedTV\logs`, sanitised, 5 files × 2 MB.
- Runs 24 h+ without leaks (test in section 13).

---

## 12. DEVELOPMENT PHASES (STRICT ORDER)

**Phase A – Clean stream in kiosk mode.** PyAV capture, fullscreen borderless window, hidden cursor, no-signal screen, auto-reconnect, sleep prevention. *Acceptance:* the known-good stream shows fullscreen on the target PC and recovers after unplugging/replugging the camera network cable; no UI controls visible.

**Phase B – TV bezel and CRT shader.** Bezel presets, screen-polygon mapping, all CRT effects with intensity controls, power-on/off, static transitions, OSD, CPU fallback. *Acceptance:* ≥ 25 FPS at 1080p on the reference PC; each effect can be toggled; screenshots for each preset.

**Phase C – Face detection (debug only).** YuNet detection + tracker, debug overlay with boxes/landmarks/FPS (`F8`). *Acceptance:* ≥ 90% detection of frontal faces at 1–3 m in normal light; stable IDs; measured detection latency reported.

**Phase D – Effects library.** Implement the filters in 7.2 with rotation modes and fade in/out. *Acceptance:* every filter follows a moving, tilting face without visible jitter; 4 simultaneous faces at ≥ 20 FPS; automatic quality downgrade works.

**Phase E – Hidden admin overlay, config, hotkeys, security.** PIN-protected overlay, Credential Manager, config validation, `reduce_motion`. *Acceptance:* all hotkeys work; wrong PIN does nothing; password never appears in logs.

**Phase F – Hardening and packaging.** 24-hour soak test, installer scripts, optional PyInstaller build, README, user manual, troubleshooting, test report. *Acceptance:* runs 24 h unattended without crash/leak; clean install on a fresh Windows 11 PC.

---

## 13. MANDATORY TEST CASES

Report results honestly. Mark every test that needs the real camera/NVR or a physical display as **"requires target hardware"** and do not claim it passed unless it was executed there.

| Test | Expected |
|---|---|
| Known-good RTSP URL (TCP) | Live video fullscreen inside the bezel |
| Password with special characters (`@ # % :`) | Connects; URL not double-encoded; password never logged |
| Wrong password / wrong channel / wrong IP | In-theme error screen + precise log reason |
| Network cable unplugged for 60 s | Static screen, then automatic recovery |
| Each TV preset, 1366x768 / 1920x1080 / 2560x1440 | Correct scaling and aspect, no clipped bezel |
| CRT effects on/off, `reduce_motion` | Effects change; no flashing > 3 Hz |
| 1, 2, 4 faces (distance 1–3 m, tilt ±30°) | Filters follow and fade in/out smoothly |
| Low light / IR night mode | Detection degrades gracefully, no crash |
| Poster/photo of a face on a wall | Documented behaviour (it may be treated as a face) |
| Filter rotation modes | Behave as configured |
| Hotkeys and PIN | Work; `Esc` does not quit |
| 24 h soak | No crash, stable memory, FPS within target |
| Privacy checks | No frames/faces written to disk; no outbound traffic except to the RTSP host |

Automated tests (no hardware): URL handling, config validation, tracker/smoothing math, effect transforms on synthetic images, shader/CPU-fallback parity on a test pattern, log sanitising. Provide a local RTSP test source (for example MediaMTX + FFmpeg test pattern) for integration tests.

---

## 14. DELIVERABLES

1. Complete source code with the structure in section 10.
2. `requirements.txt` with pinned, verified versions; `THIRD_PARTY.md` (model, fonts, assets and their licences).
3. Original or CC0 bezel and mask assets plus the generator tools.
4. Installation, start, probe and optional autostart scripts.
5. README: quick start (≤ 5 minutes), hotkey table, configuration reference, troubleshooting table, privacy notice.
6. Test report separating "executed here", "executed on target hardware" and "not executed".
7. Known limitations and roadmap (ideas: voice-reactive ghosts, PIR-triggered scares, multi-camera "channel surfing" between several TVs, recorded "found footage" mode as an explicit opt-in).
8. Version number and release notes.

---

## 15. FINAL INSTRUCTIONS

Priorities, in order: (1) the stream displays reliably fullscreen; (2) the old-TV frame and CRT look convincing at 25+ FPS; (3) faces are detected and transformed smoothly; (4) the app is unattended-safe and privacy-respecting; (5) polish and extras.

Do not invent test results, camera detections or performance numbers. Where measurement is impossible in the development environment, provide the benchmark script (`tools/benchmark.py`) and clear instructions so the operator can measure on the target PC. The finished program must run by a non-programmer: double-click to start, nothing to configure on screen, everything else hidden.

**END OF PROMPT**