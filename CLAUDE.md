# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A keyboard-driven live performance recording orchestrator. It coordinates Ableton Live (audio/MIDI) and OBS Studio (video) via hotkeys that work regardless of which application is focused. After recording multiple takes, it composites them into a grid video using FFmpeg.

## Setup

```bash
pip install -r requirements.txt
brew install ffmpeg  # macOS; Windows: winget install ffmpeg
```

External dependencies require one-time manual setup: AbletonOSC (MIDI Remote Script in Ableton) and OBS WebSocket server (port 4455). See `ableton/README.md` and `obs/README.md`.

## Running

```bash
python controller.py          # Start the hotkey controller
python test_connections.py    # Verify OBS and Ableton are reachable
python produce.py <session/>  # Manually produce a grid video
```

Windows one-click launch: `.\launch.ps1`

## Architecture

**`controller.py`** — Global hotkey listener (pynput) with a simple state machine (`IDLE` / `RECORDING`). On each keypress it sends:
- OSC UDP messages (port 11001) → Ableton via AbletonOSC (arm tracks, start/stop record, tap tempo, metronome)
- WebSocket messages (port 4455) → OBS (start/stop recording, set output directory)
- Filesystem operations (create timestamped session folders, track take counts)

**`produce.py`** — Called by controller on `p` keypress (or manually). Finds all `trackN_takeM.mp4` files and `mix.wav` in the session folder, selects an FFmpeg grid layout (1=fullscreen, 2=side-by-side, 3=2+1, 4=2×2), then encodes `final_<timestamp>.mp4`.

**`config.yaml`** — Central config: OBS connection, Ableton OSC port, session base path, video encoding settings (CRF, cell resolution, AV sync offset).

## Session Folder Layout

```
~/Music/recordings/
└── 2026-03-28_143022/
    ├── 2026-03-28_143022.als   # Ableton set (auto-saved on session create)
    ├── track1_take1.mp4        # OBS recordings per-track, per-take
    ├── track2_take1.mp4
    ├── mix.wav                 # User exports from Ableton manually
    └── final_2026-03-28_143045.mp4
```

## Hotkeys (controller.py)

| Key | Action |
|-----|--------|
| `1`–`4` | Arm track in Ableton |
| `r` | Start recording (OBS + Ableton) |
| `Space` | Stop recording / toggle playback |
| `t` | Tap tempo |
| `m` | Toggle metronome |
| `x` | Open Ableton export dialog |
| `p` | Run produce.py on current session |
| `q` | Quit |

## Platform Notes

- `controller.py` runs on both macOS and Windows. Platform is detected via `sys.platform` at the top of the file.
- **Windows**: window focus and keystrokes use PowerShell + WScript.Shell (`_PS_FOCUS_ABLETON`).
- **macOS**: window focus and keystrokes use `osascript` (AppleScript). Ableton's process name in System Events is `"Live"`. Clipboard is managed via `pbcopy`.
- `launch.ps1` is Windows-only; on macOS start Ableton and OBS manually, then run `python controller.py`.
