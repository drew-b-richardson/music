#!/usr/bin/env python3
"""
Live Performance Recording Controller
--------------------------------------
Global hotkeys (work regardless of which app is focused):

  1-4    — Arm track 1-4 in Ableton
  r      — Start recording
  Space  — Stop recording
  t      — Tap tempo
  x      — Export mix from Ableton (opens export dialog, path copied to clipboard)
  p      — Produce final video
  q      — Quit

Run with: python controller.py
Keep this terminal open during your performance.
"""

import sys
import time
import socket
import subprocess
import pathlib
import datetime
import yaml
from pynput import keyboard
import obsws_python as obs
from pythonosc.osc_message_builder import OscMessageBuilder

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
armed_track  = None     # 0-indexed track number currently armed, or None

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
        print("  Make sure OBS is running and WebSocket server is enabled (Tools -> WebSocket Server Settings).")
        sys.exit(1)

class OSCClient:
    """OSC client bound to port 11001 — AbletonOSC only accepts messages from this port."""
    def __init__(self, host, port):
        self._address = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 11001))

    def send_message(self, address, args):
        b = OscMessageBuilder(address=address)
        for a in args:
            b.add_arg(a)
        self._sock.sendto(b.build().dgram, self._address)

def make_osc_client():
    return OSCClient(ABL_HOST, ABL_PORT)

# ── Recording actions ─────────────────────────────────────────────────────────

def arm_track(track_num):
    """Arm the given track (1-4) and disarm any previously armed track."""
    global armed_track
    if state == "RECORDING":
        print("  [!] Cannot change track while recording.")
        return
    idx = track_num - 1
    if armed_track is not None and armed_track != idx:
        osc.send_message("/live/track/set/arm", [armed_track, 0])
    osc.send_message("/live/track/set/arm", [idx, 1])
    armed_track = idx
    print(f"  Track {track_num} armed")


def start_take():
    global state, session_path, take_count

    if state != "IDLE":
        return

    if armed_track is None:
        print("  [!] No track armed — press 1-4 to select a track first.")
        return

    # Create session folder on first take
    if session_path is None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        session_path = BASE_PATH / ts
        session_path.mkdir(parents=True, exist_ok=True)
        print(f"\n  Session folder: {session_path}")

    take_num = take_count + 1
    print(f"\n  ● Take {take_num} (track {armed_track + 1}) — starting...")

    # Tell OBS where to save this recording
    try:
        obs_client.set_record_directory(str(session_path))
    except Exception as e:
        print(f"  [ERROR] Could not set OBS record directory: {e}")
        return

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

    # Small buffer so Ableton finishes writing
    time.sleep(0.2)

    # Stop OBS and rename the output file to take_N.mp4
    try:
        result = obs_client.stop_record()
        output_path = pathlib.Path(result.output_path)
        dest = session_path / f"take_{take_num}.mp4"
        for _ in range(10):
            try:
                output_path.rename(dest)
                break
            except PermissionError:
                time.sleep(0.5)
        else:
            print(f"  [ERROR] Could not rename OBS output — file still locked after 5s")
    except Exception as e:
        print(f"  [ERROR] OBS stop/rename failed: {e}")

    take_count += 1
    state = "IDLE"
    print(f"  ■ Take {take_num} complete.")
    print(f"     Press r to record another take, or p to produce the final video.")


def export_mix():
    if state == "RECORDING":
        print("  [!] Stop the current recording first (Space).")
        return
    if session_path is None:
        print("  [!] No session active — record a take first.")
        return

    mix_path = session_path / "mix.wav"
    print(f"\n  ♪ Export target: {mix_path}")
    print(f"    (path copied to clipboard — paste it in Ableton's export dialog)")

    # Copy the session path to clipboard so it can be pasted in the file dialog
    subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{mix_path}'"],
                   capture_output=True)

    # Focus Ableton and send Ctrl+Shift+R via PowerShell — runs in a separate
    # process so the keystroke is never seen by pynput's listener
    subprocess.Popen(
        ["powershell", "-Command",
         "$wsh = New-Object -ComObject WScript.Shell; "
         "$wsh.AppActivate('Ableton'); "
         "Start-Sleep -Milliseconds 300; "
         "$wsh.SendKeys('^+r')"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    print(f"    Ableton export dialog opened.")
    print(f"    Paste the path, set format to WAV, then click Export.")


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
        for ext in ("aif", "aiff", "flac", "mp3"):
            candidate = session_path / f"mix.{ext}"
            if candidate.exists():
                mix_path = candidate
                break
    if not mix_path.exists():
        print(f"  [!] Mix audio not found.")
        print(f"      Export your Ableton session to:  {session_path / 'mix.wav'}")
        print(f"      Then press p again.")
        return

    print(f"\n  ► Producing final video from {take_count} take(s)...")
    try:
        subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).parent / "produce.py"),
             str(session_path)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Production failed (exit code {e.returncode}). Check FFmpeg output above.")
        return

    outputs = sorted(session_path.glob("final_*.mp4"), key=lambda p: p.stat().st_mtime)
    if outputs:
        print(f"\n  Done!  Output: {outputs[-1]}")
    else:
        print("  Production complete.")

    session_path = None
    take_count = 0
    print("  Session cleared — ready to start a new session (press r).")


# ── Keyboard listener ─────────────────────────────────────────────────────────

def on_press(key):
    try:
        ch = key.char
    except AttributeError:
        if key == keyboard.Key.space:
            stop_take()
        return

    if ch == 'r':
        start_take()
    elif ch in ('1', '2', '3', '4'):
        arm_track(int(ch))
    elif ch == 't':
        osc.send_message("/live/song/tap_tempo", [])
    elif ch == 'x':
        export_mix()
    elif ch == 'p':
        produce()
    elif ch == 'q':
        print("\n  Goodbye.")
        return False


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
    print("    1-4    — Arm track")
    print("    r      — Start recording")
    print("    Space  — Stop recording")
    print("    t      — Tap tempo")
    print("    x      — Export mix from Ableton")
    print("    p      — Produce final video")
    print("    q      — Quit")
    print()

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
