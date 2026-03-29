#!/Users/drew/repos/music/.venv/bin/python3
"""
produce.py — Build the final grid video from session takes + mix audio.

Usage:
    python produce.py [session_folder]

If session_folder is omitted, the most recent session under base_path
(from config.yaml) is used automatically.

The session folder must contain files named track{N}_take{M}.mp4 for tracks 1-4.
For each track the latest take (highest M) is used. At least one track is required.
mix.wav (or .aif/.aiff/.flac/.mp3) is optional — omit for video-only output.

Output:
    <session_folder>/final_<timestamp>.mp4
"""

import sys
import subprocess
import pathlib
import datetime
import shutil
import yaml

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

CELL_RES      = config["produce"]["cell_resolution"]   # e.g. "960x540"
VIDEO_CRF     = str(config["produce"]["video_crf"])
AUDIO_BITRATE = config["produce"]["audio_bitrate"]
AV_OFFSET     = float(config["produce"].get("av_offset", 0))

CELL_W, CELL_H = (int(x) for x in CELL_RES.split("x"))


def audio_input(mix: pathlib.Path) -> list:
    """Return FFmpeg args for the audio input, with offset applied if set."""
    args = []
    if AV_OFFSET != 0:
        args += ["-itsoffset", str(AV_OFFSET)]
    args += ["-i", str(mix)]
    return args


# ── Helpers ───────────────────────────────────────────────────────────────────

def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("[ERROR] ffmpeg not found on PATH.")
        print("  Windows: winget install ffmpeg")
        print("  macOS:   brew install ffmpeg")
        sys.exit(1)


def scale_filter(idx: int) -> str:
    """Return an ffmpeg scale filter string that forces a take to CELL_RES."""
    return f"[{idx}:v]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=decrease,pad={CELL_W}:{CELL_H}:(ow-iw)/2:(oh-ih)/2[v{idx}]"


def run_ffmpeg(args: list[str]):
    cmd = ["ffmpeg", "-y"] + args
    print("  ffmpeg " + " ".join(str(a) for a in cmd[1:]))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n[ERROR] ffmpeg exited with code {result.returncode}")
        sys.exit(result.returncode)


# ── Grid builders ──────────────────────────────────────────────────────────────

def build_1(takes: list[pathlib.Path], mix: pathlib.Path, out: pathlib.Path):
    """1 take: replace audio with mix, copy video stream."""
    run_ffmpeg([
        "-i", str(takes[0]),
        *audio_input(mix),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(out),
    ])


def build_2(takes: list[pathlib.Path], mix: pathlib.Path, out: pathlib.Path):
    """2 takes: side by side (hstack)."""
    inputs = [arg for t in takes for arg in ("-i", str(t))]
    scale_filters = ";".join(scale_filter(i) for i in range(2))
    filter_complex = f"{scale_filters};[v0][v1]hstack=inputs=2[vout]"
    run_ffmpeg(
        inputs + audio_input(mix) + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "2:a",
        "-c:v", "libx264",
        "-crf", VIDEO_CRF,
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        str(out),
    ])


def build_3(takes: list[pathlib.Path], mix: pathlib.Path, out: pathlib.Path):
    """3 takes: 2 on top row, 1 centred on bottom row (padded to full width)."""
    inputs = [arg for t in takes for arg in ("-i", str(t))]
    total_w = CELL_W * 2
    scale_filters = ";".join(scale_filter(i) for i in range(3))
    filter_complex = (
        f"{scale_filters};"
        f"[v0][v1]hstack=inputs=2[top];"
        f"[v2]pad={total_w}:{CELL_H}:(ow-iw)/2:0[bot];"
        f"[top][bot]vstack=inputs=2[vout]"
    )
    run_ffmpeg(
        inputs + audio_input(mix) + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "3:a",
        "-c:v", "libx264",
        "-crf", VIDEO_CRF,
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        str(out),
    ])


def build_4(takes: list[pathlib.Path], mix: pathlib.Path, out: pathlib.Path):
    """4 takes: 2x2 grid via xstack."""
    inputs = [arg for t in takes for arg in ("-i", str(t))]
    scale_filters = ";".join(scale_filter(i) for i in range(4))
    layout = "0_0|w0_0|0_h0|w0_h0"
    filter_complex = (
        f"{scale_filters};"
        f"[v0][v1][v2][v3]xstack=inputs=4:layout={layout}[vout]"
    )
    run_ffmpeg(
        inputs + audio_input(mix) + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "4:a",
        "-c:v", "libx264",
        "-crf", VIDEO_CRF,
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-shortest",
        str(out),
    ])


BUILDERS = {1: build_1, 2: build_2, 3: build_3, 4: build_4}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    check_ffmpeg()

    if len(sys.argv) >= 2:
        session = pathlib.Path(sys.argv[1]).expanduser().resolve()
        if not session.is_dir():
            print(f"[ERROR] Session folder not found: {session}")
            sys.exit(1)
    else:
        base = pathlib.Path(config["sessions"]["base_path"]).expanduser()
        candidates = sorted(
            (p for p in base.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            print(f"[ERROR] No session folders found in {base}")
            sys.exit(1)
        session = candidates[-1]
        print(f"  Auto-selected session: {session.name}")

    # Find the latest take for each track (track1_take*.mp4, track2_take*.mp4, ...)
    takes = []
    for track_num in range(1, 5):
        for ext in ("mp4", "mkv"):
            candidates = sorted(
                session.glob(f"track{track_num}_take*.{ext}"),
                key=lambda p: int(p.stem.split("_take")[1]) if "_take" in p.stem else 0,
            )
            if candidates:
                takes.append(candidates[-1])
                break

    if not takes:
        print(f"[ERROR] No take files (track1_take*.mp4 …) found in: {session}")
        sys.exit(1)

    # Find mix audio (required)
    mix = None
    for ext in ("wav", "aif", "aiff", "flac", "mp3"):
        candidate = session / f"mix.{ext}"
        if candidate.exists():
            mix = candidate
            break
    if not mix:
        print(f"[ERROR] Mix audio not found in {session}")
        print(f"        Export from Ableton and save as mix.wav in that folder.")
        sys.exit(1)

    n = len(takes)
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = session / f"final_{ts}.mp4"

    print(f"\n  Session : {session}")
    print(f"  Takes   : {n}  ({', '.join(t.name for t in takes)})")
    print(f"  Mix     : {mix.name}")
    print(f"  Output  : {out.name}")
    print(f"  Grid    : {['full frame', 'side by side', '2+1 grid', '2×2 grid'][n - 1]}")
    print()

    builder = BUILDERS[n]
    builder(takes, mix, out)

    print(f"\n  Done! → {out}")


if __name__ == "__main__":
    main()
