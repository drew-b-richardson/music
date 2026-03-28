# OBS Studio Setup

OBS Studio 28+ includes a built-in WebSocket server (v5) that the controller script uses to start and stop recordings programmatically.

---

## Installation

Download OBS Studio 28 or later from: https://obsproject.com

---

## One-Time Configuration

### 1. Enable WebSocket Server

1. Open OBS
2. Go to **Tools → WebSocket Server Settings**
3. Check **Enable WebSocket server**
4. Port: `4455` (default — leave as-is unless it conflicts)
5. If you want a password: enable **Enable Authentication** and set a password, then update `config.yaml` in this repo
6. Click **Apply**

### 2. Set Recording Format to MP4

1. Go to **Settings → Output → Recording**
2. Set **Recording Format** to `mp4`
   - Note: MKV is safer against crashes, but MP4 is required by the produce script. If you prefer MKV safety, you can enable **Settings → Advanced → Automatically remux to mp4** and produce.py will also accept `.mkv` files.

### 3. Set Recording Quality

Recommended settings for a high-quality webcam capture:

| Setting | Value |
|---------|-------|
| Recording Quality | High Quality, Medium File Size |
| Encoder | x264 (or hardware encoder if available) |
| Rate Control | CRF |
| CRF | 18–22 |

### 4. Configure Your Webcam Scene

1. In the **Scenes** panel, click `+` to create a scene named `Performance`
2. In the **Sources** panel, click `+` → **Video Capture Device**
3. Select your webcam and click OK
4. Resize/position the webcam feed to fill the canvas (1920×1080 recommended)
5. Optionally add a background or overlay

The controller script will direct OBS to save each take to the session folder automatically.

---

## Canvas Resolution

Set your canvas to match the grid output size. Since produce.py defaults to 960×540 per cell (1920×1080 total for 2×2):

1. **Settings → Video**
2. **Base (Canvas) Resolution**: `1920x1080`
3. **Output (Scaled) Resolution**: `1920x1080`
4. **Common FPS Values**: `30` or `60`

---

## Verify WebSocket is Working

After enabling the WebSocket server, test the connection:

```bash
python3 -c "
import obsws_python as obs
cl = obs.ReqClient(host='localhost', port=4455, timeout=3)
v = cl.get_version()
print(f'Connected! OBS {v.obs_version}')
"
```

---

## Troubleshooting

**Connection refused**
- Make sure OBS is running and WebSocket server is enabled
- Check that port 4455 isn't blocked by your firewall

**Authentication failed**
- Update `obs.password` in `config.yaml` to match what you set in OBS

**Recording saves to wrong location**
- The controller sets the recording directory automatically via WebSocket before each take
- If this fails silently, check the OBS log (Help → Log Files → Show Current Log)

**MP4 file is corrupted after a crash**
- Enable **Automatically remux to mp4** in OBS Settings → Advanced, and record in MKV format for safety. The produce.py script accepts both `.mp4` and `.mkv` take files.
