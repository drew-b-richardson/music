#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# launch.sh  —  Start Ableton, OBS, and the recording controller
# ─────────────────────────────────────────────────────────────────

ABLETON_APP="/Applications/Ableton Live 12 Suite.app"
OBS_APP="/Applications/OBS.app"
OBS_PORT=4455   # must match obs.port in config.yaml

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
CONTROLLER="$SCRIPT_DIR/controller.py"

# ── Launch apps if not already running ───────────────────────────

if ! pgrep -x "Live" > /dev/null; then
    echo "Starting Ableton..."
    open "$ABLETON_APP"
else
    echo "Ableton already running."
fi

if ! pgrep -x "OBS" > /dev/null; then
    echo "Starting OBS..."
    open "$OBS_APP"
else
    echo "OBS already running."
fi

# ── Wait for Ableton to finish loading ───────────────────────────

echo -n "Waiting for Ableton to load..."
while ! pgrep -x "Live" > /dev/null; do
    echo -n "."
    sleep 1
done
# Give Ableton time to fully initialise after the process appears
sleep 5
echo " ready."

# ── Wait for OBS WebSocket ────────────────────────────────────────

echo -n "Waiting for OBS WebSocket..."
while ! nc -z localhost "$OBS_PORT" 2>/dev/null; do
    echo -n "."
    sleep 0.5
done
echo " ready."

# ── Launch controller in a new Terminal window ───────────────────

echo "Launching controller..."
osascript -e "
tell application \"Terminal\"
    activate
    do script \"$VENV_PYTHON $CONTROLLER\"
end tell
"
