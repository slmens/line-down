"""Warn when a collector has stopped: a macOS notification plus a log line.

Usage: python3 collectors/check_fresh.py   (launchd runs it every 5 minutes)

shortcut: runs on the same Mac, so it cannot warn if the Mac itself is off or asleep;
add an outside heartbeat (e.g. healthchecks.io) if that starts happening.
"""
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import RAW

# feed folder -> seconds without a successful run before warning
LIMITS = {
    "bikeshare/station_status": 600,
    "bikeshare/station_information": 2 * 3600 + 600,
    "ttc/live_alerts": 600,
}


def stale(raw=RAW, now=None):
    """Return [(feed, age_seconds or None if never succeeded)] for feeds past their limit."""
    now = time.time() if now is None else now
    out = []
    for feed, limit in LIMITS.items():
        last = raw / feed / "LAST"
        age = now - last.stat().st_mtime if last.exists() else None
        if age is None or age > limit:
            out.append((feed, age))
    return out


def main():
    for feed, age in stale():
        msg = f"{feed}: never succeeded" if age is None else f"{feed}: no data for {int(age // 60)} min"
        print(f"{datetime.now(timezone.utc).isoformat()} STALE {msg}", file=sys.stderr)
        # msg is built only from our own constants and numbers, never from downloaded data
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Line Down collector stopped"'])


if __name__ == "__main__":
    main()
