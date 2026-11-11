"""Warn when a collector has stopped: a macOS notification plus a log line.

Usage: python3 collectors/check_fresh.py   (launchd runs it every 5 minutes)

Outside heartbeat: if data/heartbeat_url exists (e.g. a healthchecks.io ping URL) and
every feed is fresh, it is pinged. When the Mac is off, asleep or a feed has stopped,
the pings stop and the outside service raises the alarm. The URL is kept out of git:
anyone holding it could fake a ping.
"""
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import RAW, fetch

HEARTBEAT_URL_FILE = RAW.parent / "heartbeat_url"

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


def heartbeat(url_file=HEARTBEAT_URL_FILE):
    """Ping the outside heartbeat URL, if one is configured. Never raises."""
    if not url_file.exists():
        return
    try:
        fetch(url_file.read_text().strip())  # HTTPS only, no redirects off its host
    except Exception as e:
        print(f"{datetime.now(timezone.utc).isoformat()} heartbeat failed: {e!r}", file=sys.stderr)


def main():
    problems = stale()
    for feed, age in problems:
        msg = f"{feed}: never succeeded" if age is None else f"{feed}: no data for {int(age // 60)} min"
        print(f"{datetime.now(timezone.utc).isoformat()} STALE {msg}", file=sys.stderr)
        # msg is built only from our own constants and numbers, never from downloaded data
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Line Down collector stopped"'])
    if not problems:
        heartbeat()


if __name__ == "__main__":
    main()
