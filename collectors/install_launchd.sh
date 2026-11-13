#!/bin/sh
# Install (or reinstall) the launchd jobs that run the collectors and history download on this Mac.
# launchd starts them at login, after a reboot, and never runs two copies at once.
# Uninstall: launchctl bootout gui/$(id -u)/com.linedown.<name>; rm ~/Library/LaunchAgents/com.linedown.*.plist
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$REPO/data/logs"
AGENTS="$HOME/Library/LaunchAgents"
PYTHON=/usr/bin/python3  # collectors stay on system Python, stdlib only
mkdir -p "$LOGS" "$AGENTS"

install_job() { # name interval_seconds script_path [arg]
  label="com.linedown.$1"
  plist="$AGENTS/$label.plist"
  arg=""
  [ $# -ge 4 ] && arg="<string>$4</string>"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$REPO/$3</string>
    $arg
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartInterval</key><integer>$2</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$1.log</string>
</dict>
</plist>
EOF
  plutil -lint -s "$plist"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "installed $label: $3 ${4:-} every $2s, log $LOGS/$1.log"
}

install_job bikeshare-status 30 collectors/bikeshare.py station_status
install_job bikeshare-info 3600 collectors/bikeshare.py station_information  # station locations change rarely
install_job ttc-alerts 30 collectors/ttc.py
install_job check-fresh 300 collectors/check_fresh.py
install_job download-history 604800 pipelines/download_history.py  # weekly; city publishes monthly
PYTHON="$REPO/.venv/bin/python"  # the agent needs DuckDB
install_job agent-brief 60 agent/brief.py
