#!/usr/bin/env python3
"""
Live Performance Recording Controller
--------------------------------------
Global hotkeys (work regardless of which app is focused):

  r      — Start recording (creates a new take in the current session)
  Space  — Stop recording
  p      — Produce final video from all takes in the current session
  q      — Quit

Run with: python controller.py
Keep this terminal open during your performance.
"""

import sys
import time
import subprocess
import pathlib
import datetime
import yaml
from pynput import keyboard
import obsws_python as obs
from pythonosc import udp_client

# ── Load config ──────────────────────────────────────────────────────────────

CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

OBS_HOST     = config["obs"]["host"]
OBS_PORT     = config["obs"]["port"]
OBS_PASSWORD = config["obs"]["password"]
ABL_HOST     = config["ableton"]["host"]
ABL_PORT     = config["ableton"]["port"]
BASE_PATH    = pathlib.Path(config["sessions"]["base_path"]).expanduser()

# ── State ─────────────────────────────────────────────────────────────────────

state        = "IDLE"   # "IDLE" | "RECORDING"
session_path = None
take_count   = 0

# ── Connections ───────────────────────────────────────────────────────────────

def connect_obs():
    try:
        kwargs = dict(host=OBS_HOST, port=OBS_PORT, timeout=3)
        if OBS_PASSWORD:
            kwargs["password"] = OBS_PASSWORD
        client = obs.ReqClient(**kwargs)
        ver = client.get_version()
        print(f"  OBS connected  (OBS {ver.obs_version}, WebSocket {ver.obs_web_socket_version})")
        return client
    except Exception as e:
        print(f"  [ERROR] Could not connect to OBS: {e}")
        print("  Make sure OBS is running and WebSocket server is enabled (Tools → WebSocket Server Settings).")
        sys.exit(1)

def make_osc_client():
    return udp_client.SimpleUDPClient(ABL_HOST, ABL_PORT)

# ── Recording actions ─────────────────────────────────────────────────────────

def start_take():
    global state, session_path, take_count

    if state != "IDLE":
        return

    # Create session folder on first take
    if session_path is None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        session_path = BASE_PATH / ts
        session_path.mkdir(parents=True, exist_ok=True)
        print(f"\n  Session folder: {session_path}")

    take_num = take_count + 1
    print(f"\n  ● Take {take_num} — starting...")

    # Tell OBS where to save this recording
    try:
        obs_client.set_record_directory(str(session_path))
    except Exception:
        # Older obsws-python versions use a different call; fall back silently.
        pass

    # Arm the Ableton track for this take (0-indexed)
    osc.send_message("/live/track/set/arm", [take_count, 1])

    # Enable arrangement record mode in Ableton
    osc.send_message("/live/song/set/record_mode", [1])

    # Start OBS recording first (slight head-start so video is ready)
    try:
        obs_client.start_record()
    except Exception as e:
        print(f"  [ERROR] OBS start failed: {e}")
        return

    # Small buffer to let OBS settle before audio starts
    time.sleep(0.1)

    # Start Ableton playback (arrangement recording begins because record_mode=1)
    osc.send_message("/live/song/start_playing", [])

    state = "RECORDING"
    print(f"  ● Take {take_num} recording — press Space to stop")


def stop_take():
    global state, take_count

    if state != "RECORDING":
        return

    take_num = take_count + 1
    print(f"\n  ■ Stopping take {take_num}...")

    # Stop Ableton first so audio ends cleanly before video stops
    osc.send_message("/live/song/stop_playing", [])

    # Disarm the track
    osc.send_message("/live/track/set/arm", [take_count, 0])

    # Small buffer so Ableton finishes writing
    time.sleep(0.2)

    # Stop OBS
    try:
        obs_client.stop_record()
    except Exception as e:
        print(f"  [ERROR] OBS stop failed: {e}")

    take_count += 1
    state = "IDLE"

    remaining = 4 - take_count
    if remaining > 0:
        print(f"  ■ Take {take_num} complete  ({take_count}/4 recorded)")
        print(f"     Press r to record the next part, or p to produce with {take_count} take(s).")
    else:
        print(f"  ■ All 4 takes recorded.")
        print(f"     Export your Ableton mix to:  {session_path / 'mix.wav'}")
        print(f"     Then press p to produce the final video.")


def produce():
    global session_path, take_count

    if state == "RECORDING":
        print("  [!] Stop the current recording first (Space).")
        return

    if session_path is None or take_count == 0:
        print("  [!] No takes recorded in this session yet.")
        return

    mix_path = session_path / "mix.wav"
    if not mix_path.exists():
        print(f"  [!] Mix audio not found at: {mix_path}")
        print(f"      Export your Ableton session to that path, then press p again.")
        return

    print(f"\n  ► Producing final video from {take_count} take(s)...")
    try:
        result = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).parent / "produce.py"),
             str(session_path)],
            check=True,
            capture_output=False,
        )
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Production failed (exit code {e.returncode}). Check FFmpeg output above.")
        return

    # Find the output file
    outputs = sorted(session_path.glob("final_*.mp4"), key=lambda p: p.stat().st_mtime)
    if outputs:
        print(f"\n  ✓ Done!  Output: {outputs[-1]}")
    else:
        print("  ✓ Production complete.")

    # Reset session so a new session can begin
    session_path = None
    take_count = 0
    print("  Session cleared — ready to start a new session (press r).")


# ── Keyboard listener ─────────────────────────────────────────────────────────

def on_press(key):
    try:
        ch = key.char
    except AttributeError:
        # Special key — check for Space
        if key == keyboard.Key.space:
            stop_take()
        return

    if ch == 'r':
        start_take()
    elif ch == 'p':
        produce()
    elif ch == 'q':
        print("\n  Goodbye.")
        return False  # Stop listener


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    print("\n  Live Performance Recording Controller")
    print("  ─────────────────────────────────────")
    print("  Connecting to OBS and Ableton...")

    obs_client = connect_obs()
    osc        = make_osc_client()
    print(f"  Ableton OSC client ready  ({ABL_HOST}:{ABL_PORT})")
    print()
    print("  Ready.  Hotkeys:")
    print("    r      — Start recording a take")
    print("    Space  — Stop recording")
    print("    p      — Produce final video")
    print("    q      — Quit")
    print()

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
