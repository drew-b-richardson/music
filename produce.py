#!/usr/bin/env python3
"""
produce.py — Build the final grid video from session takes + Ableton mix audio.

Usage:
    python produce.py <session_folder>

The session folder must contain:
    take_1.mp4  (required)
    take_2.mp4  (optional)
    take_3.mp4  (optional)
    take_4.mp4  (optional)
    mix.wav     (required — Ableton export)

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
    """1 take: audio replacement only, no re-encode of video."""
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
    if len(sys.argv) < 2:
        print(f"Usage: python {pathlib.Path(__file__).name} <session_folder>")
        sys.exit(1)

    check_ffmpeg()

    session = pathlib.Path(sys.argv[1]).expanduser().resolve()
    if not session.is_dir():
        print(f"[ERROR] Session folder not found: {session}")
        sys.exit(1)

    # Find takes
    takes = sorted(
        (p for p in (session / f"take_{i}.mp4" for i in range(1, 5)) if p.exists())
    )
    if not takes:
        # Also accept .mkv in case OBS was set to MKV
        takes = sorted(
            (p for p in (session / f"take_{i}.mkv" for i in range(1, 5)) if p.exists())
        )

    if not takes:
        print(f"[ERROR] No take files (take_1.mp4 … take_4.mp4) found in: {session}")
        sys.exit(1)

    # Find mix audio
    mix = session / "mix.wav"
    if not mix.exists():
        # Also accept .aif / .aiff / .flac
        for ext in ("aif", "aiff", "flac", "mp3"):
            candidate = session / f"mix.{ext}"
            if candidate.exists():
                mix = candidate
                break
    if not mix.exists():
        print(f"[ERROR] Mix audio not found. Export from Ableton to: {session / 'mix.wav'}")
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
