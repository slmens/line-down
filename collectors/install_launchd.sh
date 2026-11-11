#!/bin/sh
# Install (or reinstall) the launchd jobs that run the bike share collector on this Mac.
# launchd starts them at login, after a reboot, and never runs two copies at once.
# Uninstall: launchctl bootout gui/$(id -u)/com.linedown.<name>; rm ~/Library/LaunchAgents/com.linedown.*.plist
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$REPO/data/logs"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LOGS" "$AGENTS"

install_job() { # name feed interval_seconds
  label="com.linedown.$1"
  plist="$AGENTS/$label.plist"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$REPO/collectors/bikeshare.py</string>
    <string>$2</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartInterval</key><integer>$3</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$1.log</string>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "installed $label: $2 every $3s, log $LOGS/$1.log"
}

install_job bikeshare-status station_status 30
install_job bikeshare-info station_information 3600  # station locations change rarely
