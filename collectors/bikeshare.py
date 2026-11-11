"""Save one snapshot of a Bike Share Toronto GBFS feed, exactly as it arrived.

Usage: python3 collectors/bikeshare.py station_status|station_information

launchd runs this on a timer. Each run is one fetch, so a failed fetch just exits
non-zero and the next scheduled run is the retry. No loop to crash.
"""
import json
import sys

from common import RAW, fetch, run, store

BASE = "https://toronto.publicbikesystem.net/customer/gbfs/v2/en/"
FEEDS = ("station_status", "station_information")


def save(feed, body, raw=RAW):
    """Validate and store one response under its last_updated time. Returns the path, or None if a repeat."""
    doc = json.loads(body)
    last_updated = int(doc["last_updated"])
    stations = doc["data"]["stations"]
    if not isinstance(stations, list) or not stations:
        raise ValueError("no stations list: not the expected GBFS feed")
    return store(raw / "bikeshare" / feed, str(last_updated), last_updated, body)


def main(argv):
    feed = argv[1] if len(argv) > 1 else ""
    if feed not in FEEDS:
        sys.exit(f"usage: bikeshare.py {'|'.join(FEEDS)}")
    run(feed, lambda: save(feed, fetch(BASE + feed)))


if __name__ == "__main__":
    main(sys.argv)
