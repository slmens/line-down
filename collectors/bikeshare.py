"""Save one snapshot of a Bike Share Toronto GBFS feed, exactly as it arrived.

Usage: python3 collectors/bikeshare.py station_status|station_information

launchd runs this on a timer. Each run is one fetch, so a failed fetch just exits
non-zero and the next scheduled run is the retry. No loop to crash.
"""
import gzip
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://toronto.publicbikesystem.net/customer/gbfs/v2/en/"
FEEDS = ("station_status", "station_information")
RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "bikeshare"


def fetch(feed):
    req = urllib.request.Request(BASE + feed, headers={"User-Agent": "line-down-collector"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def save(feed, body, raw=RAW):
    """Store body under its feed's last_updated time. Returns the path, or None if already stored."""
    last_updated = int(json.loads(body)["last_updated"])  # raises on a malformed response
    day = datetime.fromtimestamp(last_updated, timezone.utc).strftime("%Y-%m-%d")
    path = raw / feed / day / f"{last_updated}.json.gz"
    if path.exists():  # the feed repeated itself: store it once
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(body))
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written snapshot
    return path


def main(argv):
    feed = argv[1] if len(argv) > 1 else ""
    if feed not in FEEDS:
        sys.exit(f"usage: bikeshare.py {'|'.join(FEEDS)}")
    try:
        save(feed, fetch(feed))
    except Exception as e:  # one line per failure keeps the log readable during long outages
        print(f"{datetime.now(timezone.utc).isoformat()} {feed} failed: {e!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
