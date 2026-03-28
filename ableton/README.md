# AbletonOSC Setup

AbletonOSC is a free MIDI Remote Script that exposes Ableton Live's transport and track controls over OSC (UDP). The controller script uses it to start and stop arrangement recording.

**Requires Ableton Live 11 or later.**

---

## Installation

### 1. Download AbletonOSC

Go to: https://github.com/ideoforms/AbletonOSC/releases

Download the latest release ZIP and extract it. You should have a folder called `AbletonOSC`.

### 2. Copy to Ableton's Remote Scripts folder

| Platform | Path |
|----------|------|
| Windows  | `C:\Users\<YourName>\Documents\Ableton\User Library\Remote Scripts\` |
| macOS    | `~/Music/Ableton/User Library/Remote Scripts/` |

Copy the entire `AbletonOSC` folder into that `Remote Scripts` directory.

The result should look like:
```
Remote Scripts/
└── AbletonOSC/
    ├── __init__.py
    └── ...
```

### 3. Enable in Ableton

1. Open Ableton Live
2. Go to **Preferences → Link, Tempo & MIDI** (Windows: Ctrl+,  macOS: Cmd+,)
3. Under **Control Surfaces**, click a slot that says "None"
4. Choose **AbletonOSC** from the dropdown
5. Close Preferences

You should see a message in the Ableton status bar confirming AbletonOSC loaded.

---

## Verify It's Working

AbletonOSC listens on **port 11000** (UDP) by default.

You can test it from the terminal:

```bash
# Install a quick OSC test tool
pip install python-osc

python3 -c "
from pythonosc import udp_client
c = udp_client.SimpleUDPClient('127.0.0.1', 11000)
c.send_message('/live/song/get/tempo', [])
print('Message sent — check Ableton status bar for activity')
"
```

---

## How the Controller Uses AbletonOSC

| Action | OSC Message |
|--------|-------------|
| Arm track N for recording | `/live/track/set/arm [N, 1]` |
| Disarm track N | `/live/track/set/arm [N, 0]` |
| Enable arrangement record mode | `/live/song/set/record_mode [1]` |
| Start playback (triggers recording) | `/live/song/start_playing []` |
| Stop playback (stops recording) | `/live/song/stop_playing []` |

---

## Ableton Project Setup

For the cleanest workflow, set up your Ableton project before recording:

1. Create 4 audio tracks (one per part you'll record)
2. Set each track's input to your audio interface / microphone
3. Set the arrangement view as your main view
4. Optionally set a metronome / click track so each take stays in time

The controller automatically arms track 1 for take 1, track 2 for take 2, etc. (0-indexed internally).

---

## Troubleshooting

**AbletonOSC doesn't appear in Control Surfaces dropdown**
- Make sure the folder is named exactly `AbletonOSC` (no spaces, correct capitalisation)
- Restart Ableton after copying the files

**Recording doesn't start in Ableton**
- Confirm AbletonOSC is selected in Preferences → Control Surfaces
- Check that port 11000 is not blocked by a firewall
- Make sure you're in Arrangement view (not Session view) for linear recording
