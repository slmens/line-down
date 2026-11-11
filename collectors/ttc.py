"""Save one snapshot of the TTC live alerts feed (the JSON behind ttc.ca service alerts).

Usage: python3 collectors/ttc.py

Stored only when the content changes. The feed's own lastUpdated is not used: it is
Toronto local time mislabelled as UTC ("Z"), so files are named by our fetch time.
"""
import hashlib
import json
import time

from common import RAW, fetch, run, store

URL = "https://alerts.ttc.ca/api/alerts/live-alerts"


def save(body, now, raw=RAW):
    """Validate and store one response. Returns the path, or None if unchanged since the last one."""
    doc = json.loads(body)
    if not isinstance(doc.get("routes"), list) or not isinstance(doc.get("lastUpdated"), str):
        raise ValueError("no routes list: not the expected TTC alerts feed")
    return store(raw / "ttc" / "live_alerts", hashlib.sha256(body).hexdigest(), now, body)


if __name__ == "__main__":
    run("ttc_live_alerts", lambda: save(fetch(URL), time.time()))
