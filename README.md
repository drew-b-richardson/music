# Live Performance Recording

Keyboard-driven workflow for recording multi-part musical performances with synchronized audio (Ableton Live) and video (OBS), then compositing a professional grid video with FFmpeg.

## Workflow

```
r      — Start recording a take  (creates session folder on first press)
Space  — Stop recording
p      — Produce final video

Repeat r / Space for each part (up to 4), then export the Ableton mix, then press p.
```

The final output is a 2×2 grid video (or side-by-side / full-frame for fewer takes) with your Ableton mix as the audio track.

```
~/Music/recordings/
└── 2026-03-28_143022/
    ├── take_1.mp4          ← OBS recording, part 1
    ├── take_2.mp4          ← OBS recording, part 2
    ├── take_3.mp4          ← OBS recording, part 3
    ├── take_4.mp4          ← OBS recording, part 4
    ├── mix.wav             ← You export this from Ableton
    └── final_*.mp4         ← Produced by pressing p
```

---

## One-Time Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install FFmpeg

| Platform | Command |
|----------|---------|
| Windows  | `winget install ffmpeg` |
| macOS    | `brew install ffmpeg` |

Verify: `ffmpeg -version`

### 3. Set up AbletonOSC

See [ableton/README.md](ableton/README.md)

### 4. Set up OBS

See [obs/README.md](obs/README.md)

### 5. Edit config.yaml (optional)

Open `config.yaml` and adjust:
- `obs.password` — if you set a WebSocket password in OBS
- `sessions.base_path` — where session folders are created (default: `~/Music/recordings`)
- `produce.cell_resolution` — grid cell size (default: `960x540` → 1920×1080 total)

---

## Running

```bash
python controller.py
```

Keep this terminal open during your performance. The script connects to OBS and Ableton on startup and confirms both are reachable before you begin.

---

## Ableton Export Step

After recording all takes, export your Ableton session mix:

1. In Ableton: **File → Export Audio/Video** (or Ctrl+Shift+R / Cmd+Shift+R)
2. Set the export location to your session folder (printed in the terminal when you recorded)
3. Set the filename to `mix`
4. Export format: WAV, 44.1 kHz, 24-bit (or 32-bit float)
5. Click **Export**

Then press `p` in the controller terminal to produce the final video.

---

## Producing Manually

You can also run `produce.py` directly without the controller:

```bash
python produce.py ~/Music/recordings/2026-03-28_143022/
```

---

## Requirements

| Software | Version | Notes |
|----------|---------|-------|
| Python | 3.10+ | |
| Ableton Live | Suite 11+ | Required for AbletonOSC |
| OBS Studio | 28+ | WebSocket v5 is built in |
| FFmpeg | Any recent | Must be on PATH |
