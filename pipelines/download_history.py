"""Download the historical datasets from Toronto Open Data, kept exactly as they arrived.

Usage: python3 pipelines/download_history.py

Saves to data/raw/history/<dataset>/<last-modified date>/<file>. Re-runnable: files
already downloaded are skipped. When the city updates a file (the since-2025 delay
CSV changes monthly) the new version lands in a new date folder and the old one is kept.
Nothing downloaded is unzipped or executed here.
"""
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collectors"))
from common import RAW, download, fetch  # noqa: E402

API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id="
# ttc-routes-and-schedules is the TTC's GTFS: it holds the subway station locations
DATASETS = ("ttc-subway-delay-data", "bike-share-toronto-ridership-data", "ttc-routes-and-schedules")
HOSTS = {"ckan0.cf.opendata.inter.prod-toronto.ca", "opendata.toronto.ca"}
FORMATS = {"CSV", "XLSX", "ZIP"}  # the XML/JSON copies and live datastore dumps duplicate these
MAX_FILE = 1_000_000_000  # largest file today is ~390 MB
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def plan(dataset, resources, raw=RAW):
    """Return [(url, dest)] for the files to keep. Raises on a surprising listing."""
    out = []
    for r in resources:
        url = r["url"]
        if r["format"].upper() not in FORMATS or "/datastore/dump/" in url:
            continue
        if not url.startswith("https://") or urlparse(url).netloc not in HOSTS:
            raise ValueError(f"unexpected download location: {url}")
        name = url.rsplit("/", 1)[-1]
        version = (r.get("last_modified") or r["created"])[:10]
        if not SAFE_NAME.match(name) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
            raise ValueError(f"unsafe file name or date: {name!r} {version!r}")
        out.append((url, raw / "history" / dataset / version / name))
    return out


def check(path, name):
    """Raise unless the file at path is the type its name says and, for zip/xlsx, intact.

    The portal's listed sizes are stale for some files, so completeness is checked
    against the server's Content-Length in common.download instead.
    """
    with path.open("rb") as f:
        head = f.read(4096)
    if name.endswith((".zip", ".xlsx")):
        if not head.startswith(b"PK\x03\x04"):
            raise ValueError("not a zip/xlsx file")
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()  # reads every member and checks its CRC; extracts nothing
        if bad:
            raise ValueError(f"corrupt member {bad}")
    elif b"\x00" in head or head.lstrip().startswith(b"<"):
        raise ValueError("not a plain CSV (binary or HTML)")


def main():
    failed = 0
    for dataset in DATASETS:
        resources = json.loads(fetch(API + dataset))["result"]["resources"]
        for url, dest in plan(dataset, resources):
            rel = dest.relative_to(RAW)
            if dest.exists():
                print(f"have  {rel}")
                continue
            try:
                n = download(url, dest, MAX_FILE, lambda p: check(p, dest.name))
                print(f"saved {rel} ({n / 1e6:.1f} MB)", flush=True)
            except Exception as e:
                failed += 1
                print(f"FAILED {url}: {e!r}", file=sys.stderr, flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
