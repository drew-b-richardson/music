#!/usr/bin/env python3
"""
Live Performance Recording Controller
--------------------------------------
Global hotkeys (work regardless of which app is focused):

  1-4    — Arm track 1-4 in Ableton
  r      — Start recording
  Space  — Stop recording
  t      — Tap tempo
  m      — Toggle metronome
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
ABL_HOST           = config["ableton"]["host"]
ABL_PORT           = config["ableton"]["port"]
ABL_COLLECT_STEPS  = int(config["ableton"].get("collect_menu_steps", 7))

# PowerShell snippet that finds the Ableton Live window by process title and
# activates it by PID — more reliable than AppActivate("Ableton") which does
# a partial title match and can grab whichever editor or app is also running.
_PS_FOCUS_ABLETON = (
    "$proc = Get-Process | Where-Object { $_.MainWindowTitle -like '*Ableton Live*' } "
    "| Select-Object -First 1; "
    "if (-not $proc) { Write-Error 'Ableton Live not found'; exit 1 }; "
    "$wsh = New-Object -ComObject WScript.Shell; "
    "$wsh.AppActivate($proc.Id); "
    "Start-Sleep -Milliseconds 500; "
)
BASE_PATH    = pathlib.Path(config["sessions"]["base_path"]).expanduser()

# ── State ─────────────────────────────────────────────────────────────────────

state             = "IDLE"   # "IDLE" | "RECORDING"
session_path      = None
track_takes       = {}       # track_num (1-4) -> number of takes recorded so far
armed_track       = None     # 0-indexed track number currently armed, or None
metronome_on      = False
transport_playing = False    # tracks whether Ableton transport is currently running

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


def toggle_transport():
    global transport_playing
    if transport_playing:
        osc.send_message("/live/song/stop_playing", [])
        transport_playing = False
        print("  ■ Playback stopped")
    else:
        osc.send_message("/live/song/start_playing", [])
        transport_playing = True
        print("  ► Playback started")


def start_take():
    global state, track_takes, transport_playing

    if state != "IDLE":
        return

    if armed_track is None:
        print("  [!] No track armed — press 1-4 to select a track first.")
        return

    track_num = armed_track + 1
    take_num  = track_takes.get(track_num, 0) + 1
    print(f"\n  ● Track {track_num}, take {take_num} — starting...")

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
    transport_playing = True
    print(f"  ● Track {track_num}, take {take_num} recording — press Space to stop")


def stop_take():
    global state, track_takes, transport_playing

    if state != "RECORDING":
        return

    track_num = armed_track + 1
    take_num  = track_takes.get(track_num, 0) + 1
    print(f"\n  ■ Stopping track {track_num}, take {take_num}...")

    # Stop Ableton first so audio ends cleanly before video stops
    osc.send_message("/live/song/stop_playing", [])

    # Small buffer so Ableton finishes writing
    time.sleep(0.2)

    # Stop OBS and rename the output file to track{N}_take{M}.mp4
    try:
        result = obs_client.stop_record()
        output_path = pathlib.Path(result.output_path)
        dest = session_path / f"track{track_num}_take{take_num}.mp4"
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

    track_takes[track_num] = take_num
    state = "IDLE"
    transport_playing = False
    print(f"  ■ Track {track_num}, take {take_num} saved as: track{track_num}_take{take_num}.mp4")
    print(f"     Press r to record another take, or p to produce the final video.")


def save_set_to_session():
    """Save the Ableton set into the session folder and collect all audio there.
    Uses Save As to move the project, then Collect All and Save to copy audio clips.
    Blocking — completes before recording starts so Ableton is free when OBS rolls."""
    set_filename = session_path.name + ".als"
    set_path = str(session_path / set_filename)

    # Escape WScript SendKeys special characters in the path
    escaped = set_path
    for ch in "{}+^%~()":
        escaped = escaped.replace(ch, "{" + ch + "}")

    down_presses = "{DOWN " + str(ABL_COLLECT_STEPS) + "}"

    print(f"  Saving Ableton set → {set_filename}")
    ps_cmd = (
        # ── Step 1: Save As ──────────────────────────────────────────────────
        _PS_FOCUS_ABLETON +
        "$wsh.SendKeys('^+s'); "                    # Ctrl+Shift+S — Save As
        "Start-Sleep -Milliseconds 1000; "          # wait for dialog to open
        "$wsh.SendKeys('^a'); "                     # select any existing filename text
        f"$wsh.SendKeys('{escaped}'); "             # type full destination path
        "Start-Sleep -Milliseconds 200; "
        "$wsh.SendKeys('~'); "                      # Enter — confirm save

        # ── Step 2: Collect All and Save ─────────────────────────────────────
        # Wait for Save As to fully complete, then use File menu to collect
        # all referenced audio into the session folder.
        "Start-Sleep -Milliseconds 2000; " +
        _PS_FOCUS_ABLETON +
        "$wsh.SendKeys('%f'); "                     # Alt+F — open File menu
        "Start-Sleep -Milliseconds 500; "
        "$wsh.SendKeys('c'); "                      # jump to Collect All and Save by letter
        "Start-Sleep -Milliseconds 100; "
        "$wsh.SendKeys('~')"                        # Enter — confirm
    )
    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
    print(f"  Ableton set saved and audio collected.")


def export_mix():
    if state == "RECORDING":
        print("  [!] Stop the current recording first (Space).")
        return

    mix_path = session_path / "mix.wav"
    print(f"\n  ♪ Export target: {mix_path}")
    print(f"    (folder path copied to clipboard — paste it in Ableton's export dialog)")

    # Copy the session folder path to clipboard so it can be pasted in the file dialog
    subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{session_path}'"],
                   capture_output=True)

    # Focus Ableton by PID and send Ctrl+Shift+R — runs in a separate process
    # so the keystroke is never seen by pynput's listener
    subprocess.Popen(
        ["powershell", "-Command",
         _PS_FOCUS_ABLETON +
         "$wsh.SendKeys('^+r')"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    print(f"    Ableton export dialog opened.")
    print(f"    Paste the path, set format to WAV, then click Export.")


def produce():
    global session_path, track_takes

    if state == "RECORDING":
        print("  [!] Stop the current recording first (Space).")
        return

    if not track_takes:
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

    track_summary = ", ".join(
        f"track{t}_take{track_takes[t]}" for t in sorted(track_takes)
    )
    print(f"\n  ► Producing final video using: {track_summary}")
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

    print("\n  Goodbye.")
    sys.exit(0)


# ── Keyboard listener ─────────────────────────────────────────────────────────

def on_press(key):
    try:
        ch = key.char
    except AttributeError:
        if key == keyboard.Key.space:
            if state == "RECORDING":
                stop_take()
            else:
                toggle_transport()
        return

    if ch == 'r':
        start_take()
    elif ch in ('1', '2', '3', '4'):
        arm_track(int(ch))
    elif ch == 't':
        osc.send_message("/live/song/tap_tempo", [])
    elif ch == 'm':
        global metronome_on
        metronome_on = not metronome_on
        osc.send_message("/live/song/set/metronome", [int(metronome_on)])
        print(f"  Metronome {'on' if metronome_on else 'off'}.")
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

    # Create session folder and save Ableton set into it immediately
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    session_path = BASE_PATH / ts
    session_path.mkdir(parents=True, exist_ok=True)
    print(f"\n  Session folder: {session_path}")
    save_set_to_session()

    print()
    print("  Ready.  Hotkeys:")
    print("    1-4    — Arm track")
    print("    r      — Start recording")
    print("    Space  — Stop recording / toggle playback")
    print("    t      — Tap tempo")
    print("    s      — Save Ableton set")
    print("    x      — Export mix from Ableton")
    print("    p      — Produce final video")
    print("    q      — Quit")
    print()

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
