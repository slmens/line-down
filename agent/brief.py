"""Incident briefs: when a subway disruption appears in the TTC live alerts, gather facts from
our own data, have Claude write a short brief from them, and score the brief once the alert clears.

Usage:
    .venv/bin/python agent/brief.py          process new alert snapshots (launchd runs this every minute)
    .venv/bin/python agent/brief.py score    score finished incidents -> agent/output/scores.json

A disruption is a Subway-type alert (Lines 1-6) that is not planned maintenance and says no service,
delays or reduced service. It starts at the first snapshot that shows it and ends at the first
snapshot where it is gone or says "Regular service" (snapshots are ~30 s apart when alerts change).

Claude only words the brief. Every number comes from `facts()`: the stretch from GTFS station
order, the usual length from the TTC delay log, the Bike Share effect from analysis/output, and
dock levels from the station_status snapshot taken just before the alert. Facts are frozen at alert
time, so a brief written later (e.g. after the API key is added) uses the same inputs.

Claude is called through OpenRouter. The key is read from OPENROUTER_API_KEY or
data/openrouter_api_key (launchd has no shell env).
Without one, incidents and facts are still recorded and briefs are written once a key exists.
"""
import gzip
import json
import math
import os
import re
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    ZoneInfo = None

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ALERTS = DATA / "raw" / "ttc" / "live_alerts"
STATUS = DATA / "raw" / "bikeshare" / "station_status"
DB = DATA / "warehouse" / "linedown.duckdb"
FINDING = ROOT / "analysis" / "output" / "results.json"
INCIDENTS = DATA / "agent" / "incidents"
STATE = DATA / "agent" / "state.json"
KEY_FILE = DATA / "openrouter_api_key"
OUT = Path(__file__).resolve().parent / "output"

MODEL = "anthropic/claude-haiku-5.5"  # OpenRouter id; any model on openrouter.ai/models works
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DISRUPTING = {"NO_SERVICE", "SIGNIFICANT_DELAYS", "REDUCED_SERVICE"}
NEAR_M = 500
LOW_BIKES = 2
MIN_DELAY = 5     # shortcut: an alert is assumed to mean a 5+ min delay; check against alert lengths once there are enough
MIN_SAMPLES = 30  # fewer past delays for a cause -> use all causes (as in walk_or_wait)

# Alert cause text -> TTC delay-log code prefixes. First match wins; no match -> all causes.
CAUSE_CODES = [
    ("medical", ["MUI"]),
    ("alarm", ["MUPAA", "SUEAS", "PUSEA"]),
    ("trespasser", ["SUUT"]),
    ("investigation", ["SUO"]),
    ("security", ["SU"]),
    ("police", ["SU"]),
    ("fire", ["MUPL", "MUFS"]),
    ("smoke", ["MUPL", "MUFS"]),
    ("signal", ["PUS"]),
    ("mechanical", ["EU"]),
    ("operational", ["TU", "MUTO"]),
]

SYSTEM = """You write incident briefs about Toronto subway disruptions for riders.
You get the facts as JSON for one disruption that has just started. Write 3 to 5 short sentences of plain English:
what is affected, how long delays like this usually last, how Bike Share use nearby usually changes in the first hour,
and how many bikes are at the docks nearby right now.
Use only numbers that appear in the facts, copied exactly. Do not calculate new numbers (no sums, differences, rounding or unit changes).
If a fact is null or missing, say we have no data for it instead of guessing.
No headings, no bullet points, no preamble."""


# ---------- pure helpers (tested) ----------

def is_disruption(r):
    return r.get("routeType") == "Subway" and r.get("cause") != "MAINTENANCE" and r.get("effect") in DISRUPTING


def cause_prefixes(cause_text):
    text = (cause_text or "").lower()
    return next((p for word, p in CAUSE_CODES if word in text), None)


def clean(name):
    name = name.lower().replace(" station", "").replace("'", "").replace(".", "").replace("-", " ")
    return " ".join(name.split())


def match_station(name, stations):
    """Exact cleaned name, else a unique prefix (alerts say "Vaughan" for Vaughan Metropolitan Centre)."""
    key = clean(name)
    hits = [s for s in stations if clean(s) == key] or [s for s in stations if clean(s).startswith(key)]
    return hits[0] if len(hits) == 1 else None


def stretch(start, end, line_order):
    """Stations from start to end inclusive along one line, plus any names that did not match."""
    names = [n for n in (start, end) if n]
    ends = [match_station(n, line_order) for n in names]
    unmatched = [n for n, m in zip(names, ends) if m is None]
    found = [m for m in ends if m]
    if not found:
        return [], unmatched
    idx = [line_order.index(m) for m in found]
    i, j = min(idx), max(idx)
    return line_order[i:j + 1], unmatched


def length_summary(lengths):
    lengths = sorted(lengths)
    return {"based_on_past_delays": len(lengths), "median_minutes": round(statistics.median(lengths)),
            "8_in_10_under_minutes": round(lengths[int(0.8 * (len(lengths) - 1))])}


def numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")))


def unsupported_numbers(brief, facts):
    """Numbers in the brief that appear nowhere in the facts: the faithfulness check."""
    return sorted(numbers(brief) - numbers(json.dumps(facts)), key=float)


def metres(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(a))


def local(ts):
    return datetime.fromtimestamp(ts, ZoneInfo("America/Toronto")).strftime("%Y-%m-%d %H:%M")


# ---------- facts ----------

def snapshot_files(root, since=0):
    """(unix seconds, path) of every snapshot newer than `since`, oldest first."""
    first_day = datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%d")
    out = []
    for day in root.iterdir():
        if day.is_dir() and day.name >= first_day:
            out += [(int(f.name.split(".")[0]), f) for f in day.glob("*.json.gz")]
    return sorted(x for x in out if x[0] > since)


def dock_levels(con, stations, ts):
    """Bikes at docks within NEAR_M of the stations, from the last snapshot at or before ts."""
    before = [x for x in snapshot_files(STATUS, ts - 3600) if x[0] <= ts]
    if not stations or not before:
        return None
    snap_ts, path = before[-1]
    live = {s["station_id"]: s for s in json.load(gzip.open(path))["data"]["stations"]}
    marks = con.execute("select lat, lon from subway_stations where station in (select unnest(?))",
                        [stations]).fetchall()
    near = [(str(i), n) for i, n, lat, lon in con.execute("select station_id, name, lat, lon from bike_stations").fetchall()
            if any(metres(lat, lon, a, b) <= NEAR_M for a, b in marks)]
    seen = [(n, live[i]) for i, n in near if i in live and live[i].get("is_renting")]
    low = [n for b, n in sorted((s["num_bikes_available"], n.strip()) for n, s in seen) if b <= LOW_BIKES]
    return {"stations_within_500_m": len(seen), "bikes_available": sum(s["num_bikes_available"] for _, s in seen),
            "stations_with_2_or_fewer_bikes": len(low), "low_station_names": low[:5],
            "snapshot_minutes_before_alert": round((ts - snap_ts) / 60)}


def facts(con, alert, ts):
    """(facts for the brief, all-causes median length as the scoring baseline)."""
    line = alert.get("route", "")
    order = [s for (s,) in con.execute("select station from line_stations where line = ? order by seq", [line]).fetchall()]
    stations, unmatched = stretch(alert.get("stopStart"), alert.get("stopEnd"), order)
    prefixes = cause_prefixes(alert.get("causeDescription"))
    rows = con.execute("select code, min_delay from subway_delays where line in ('1', '2', '4') and min_delay >= ?",
                       [MIN_DELAY]).fetchall()
    lengths = [m for c, m in rows if prefixes and c and c.startswith(tuple(prefixes))]
    usual = length_summary(lengths) if len(lengths) >= MIN_SAMPLES else None
    everything = length_summary([m for _, m in rows])
    if usual is None:
        usual = {**everything, "note": "no close match for this cause, so all causes"}
    usual["counting_delays_of_at_least_minutes"] = MIN_DELAY
    ring = json.loads(FINDING.read_text())["all"]["first_hour"]
    return {
        "alert_time": local(ts),
        "ttc_alert_text": alert.get("headerText") or alert.get("title"),
        "line": line,
        "effect": alert.get("effectDesc"),
        "cause": alert.get("causeDescription"),
        "affected_stations": [s.replace(" Station", "") for s in stations],
        "unmatched_stop_names": unmatched,
        "usual_length": usual,
        "bike_share_trip_change_first_hour_percent": {
            r: {"typical": round(v["lift"] * 100), "range_low": round(v["lo"] * 100), "range_high": round(v["hi"] * 100)}
            for r, v in ring.items()},
        "bikes_near_affected_stations_now": dock_levels(con, stations, ts),
    }, everything["median_minutes"]


# ---------- incidents ----------

def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)  # a crash never leaves a half-written file


def step(open_ids, routes):
    """(ids now disrupting -> alert, ids that started, ids that ended) for one snapshot."""
    current = {r["id"]: r for r in routes if is_disruption(r)}
    return current, sorted(set(current) - set(open_ids)), sorted(set(open_ids) - set(current))


def process():
    import duckdb
    state = load(STATE, {"last_ts": 0, "open": [], "pending": []})
    con = None
    for ts, path in snapshot_files(ALERTS, state["last_ts"]):
        current, started, ended = step(state["open"], json.load(gzip.open(path))["routes"])
        for aid in ended:
            inc = load(INCIDENTS / f"{aid}.json", None)
            if inc and inc.get("cleared_ts") is None:
                inc.update(cleared_ts=ts, cleared_at=local(ts), actual_minutes=round((ts - inc["first_ts"]) / 60, 1))
                save(INCIDENTS / f"{aid}.json", inc)
        for aid in started:
            if (INCIDENTS / f"{aid}.json").exists():
                continue  # same alert id back again: keep the first incident
            con = con or duckdb.connect(str(DB), read_only=True)
            f, baseline = facts(con, current[aid], ts)
            save(INCIDENTS / f"{aid}.json", {"alert_id": aid, "first_ts": ts, "first_seen": local(ts),
                                             "alert": current[aid], "facts": f, "baseline_median_minutes": baseline,
                                             "brief": None, "cleared_ts": None})
            state["pending"].append(aid)
        state.update(last_ts=ts, open=sorted(current))
        save(STATE, state)
    state["pending"] = write_briefs(state["pending"])
    save(STATE, state)


def write_briefs(pending):
    """Write briefs for pending incidents; return the ids still waiting (no key, or the API failed)."""
    key = os.environ.get("OPENROUTER_API_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not pending or not key:
        return pending
    waiting = []
    for aid in pending:
        inc = load(INCIDENTS / f"{aid}.json", None)
        if inc is None:
            continue
        try:
            r = chat(key, [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": json.dumps(inc["facts"], indent=1)}])
        except urllib.error.HTTPError as e:
            print(f"{datetime.now(timezone.utc).isoformat()} brief {aid} failed: HTTP {e.code} {e.read()[:300]!r}",
                  file=sys.stderr)
            if e.code in (401, 402, 403):  # bad key or no credits: every other call would fail the same way
                return pending
            waiting.append(aid)
            continue
        except OSError as e:  # network down: try again next run
            print(f"{datetime.now(timezone.utc).isoformat()} brief {aid} failed: {e!r}", file=sys.stderr)
            waiting.append(aid)
            continue
        choice = r["choices"][0]
        text = (choice["message"].get("content") or "").strip()
        inc.update(brief=text or None, stop_reason=choice.get("finish_reason"), model=r.get("model"),
                   unsupported_numbers=unsupported_numbers(text, inc["facts"]))
        save(INCIDENTS / f"{aid}.json", inc)
    return waiting


def chat(key, messages):
    """One OpenRouter chat completion (OpenAI-style API). Raises HTTPError on an error status."""
    body = json.dumps({"model": MODEL, "messages": messages, "max_tokens": 2000,
                       "reasoning": {"effort": "low"}}).encode()
    req = urllib.request.Request(OPENROUTER_URL, body, {"Authorization": f"Bearer {key}",
                                                       "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


# ---------- scoring ----------

def score():
    """Score cleared incidents: length vs the usual-length median and an all-causes baseline, the
    8-in-10 bound's coverage, and the share of briefs with no number missing from the facts."""
    incs = [load(p, None) for p in sorted(INCIDENTS.glob("*.json"))]
    done = [i for i in incs if i.get("actual_minutes") is not None]
    briefs = [i for i in incs if i.get("brief")]
    result = {"incidents": len(incs), "cleared": len(done), "briefs_written": len(briefs)}
    if done:
        result["length"] = {
            "mean_abs_error_minutes": round(statistics.mean(
                abs(i["actual_minutes"] - i["facts"]["usual_length"]["median_minutes"]) for i in done), 1),
            "baseline_all_causes_mean_abs_error_minutes": round(statistics.mean(
                abs(i["actual_minutes"] - i["baseline_median_minutes"]) for i in done), 1),
            "share_within_8_in_10_bound": round(statistics.mean(
                i["actual_minutes"] <= i["facts"]["usual_length"]["8_in_10_under_minutes"] for i in done), 2),
            "median_actual_minutes": statistics.median(i["actual_minutes"] for i in done)}
    if briefs:
        result["faithful_share"] = round(statistics.mean(not i["unsupported_numbers"] for i in briefs), 2)
        result["unfaithful"] = {i["alert_id"]: i["unsupported_numbers"] for i in briefs if i["unsupported_numbers"]}
    save(OUT / "scores.json", result)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    score() if sys.argv[1:] == ["score"] else process()
