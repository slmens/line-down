"""Shared fetch and storage for the collectors.

Safety model: downloads are only ever parsed as JSON and stored as gzip. Nothing
downloaded is executed, used as a file path, or passed to a shell.
"""
import gzip
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
MAX_BYTES = 10_000_000  # largest feed is ~0.6 MB; anything far bigger is not the feed


def fetch(url):
    """GET url over verified HTTPS and return the body. Raises on anything unexpected."""
    host = urlparse(url).netloc
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS url {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "line-down-collector"})
    with urllib.request.urlopen(req, timeout=20) as resp:  # verifies certificates by default
        final = urlparse(resp.geturl())
        if final.scheme != "https" or final.netloc != host:
            raise ValueError(f"redirected away from {host} to {resp.geturl()}")
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError(f"response over {MAX_BYTES} bytes")
    return body


def _write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # a crash never leaves a half-written file


def store(feed_dir, key, ts, body):
    """Save body as <feed_dir>/<UTC date>/<ts>.json.gz unless key equals the last stored key.

    <feed_dir>/LAST holds that key and is touched on every successful run, so its age
    shows when the collector last worked. Returns the path written, or None for a repeat.
    """
    last = feed_dir / "LAST"
    if last.exists() and last.read_text() == key:
        last.touch()
        return None
    day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    path = feed_dir / day / f"{int(ts)}.json.gz"
    _write_atomic(path, gzip.compress(body))
    _write_atomic(last, key.encode())
    return path


def run(label, job):
    """Run one collection; on failure log one line and exit non-zero (the next scheduled run retries)."""
    try:
        job()
    except Exception as e:
        print(f"{datetime.now(timezone.utc).isoformat()} {label} failed: {e!r}", file=sys.stderr)
        sys.exit(1)
