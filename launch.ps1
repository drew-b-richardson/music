# ─────────────────────────────────────────────────────────────────
# launch.ps1  —  Start Ableton, OBS, and the recording controller
# ─────────────────────────────────────────────────────────────────

$AbletonExe     = "C:\ProgramData\Ableton\Live 12 Suite\Program\Ableton Live 12 Suite.exe"
$AbletonProject = "C:\path\to\your\project.als"   # <-- set this to your .als file
$OBSExe         = "C:\Program Files\obs-studio\bin\64bit\obs64.exe"
$OBSPort        = 4455    # must match obs.port in config.yaml
$ScriptDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$Controller     = Join-Path $ScriptDir "controller.py"

# ── Launch apps if not already running ───────────────────────────

if (-not (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $AbletonExe })) {
    Write-Host "Starting Ableton..."
    Start-Process $AbletonExe -ArgumentList "`"$AbletonProject`""
} else {
    Write-Host "Ableton already running."
}

if (-not (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "obs*" })) {
    Write-Host "Starting OBS..."
    Start-Process $OBSExe -WorkingDirectory (Split-Path $OBSExe)
} else {
    Write-Host "OBS already running."
}

# ── Wait for Ableton (watch for its window title) ────────────────

Write-Host "Waiting for Ableton to load..." -NoNewline
while ($true) {
    $proc = Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -like "*Ableton Live*" }
    if ($proc) { break }
    Write-Host "." -NoNewline
    Start-Sleep -Milliseconds 1000
}
Write-Host " ready."

# ── Wait for OBS WebSocket ────────────────────────────────────────

Write-Host "Waiting for OBS WebSocket..." -NoNewline
while ($true) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("localhost", $OBSPort)
        $tcp.Close()
        break
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Milliseconds 500
    }
}
Write-Host " ready."

# ── Launch controller in a new terminal window ───────────────────

Write-Host "Launching controller..."
Start-Process "cmd.exe" -ArgumentList "/k python `"$Controller`""
