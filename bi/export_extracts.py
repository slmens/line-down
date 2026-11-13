"""Write the CSV extracts the Tableau Public dashboards read (Tableau Public cannot open DuckDB).

    .venv/bin/python bi/export_extracts.py        writes data/exports/*.csv (Dagster: tableau_extracts)

Every file is small and aggregated (Tableau Public allows 15M rows per source). What each
dashboard shows, and how, is in bi/TABLEAU.md.
"""
import csv
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "exports"
DB = ROOT / "data" / "warehouse" / "linedown.duckdb"
RESULTS = ROOT / "analysis" / "output" / "results.json"
INCIDENTS = ROOT / "data" / "agent" / "incidents"


def finding_rows(results):
    """(first-hour rows, over-time rows) from analysis/output/results.json; lifts are fractions (0.136 = +13.6%)."""
    first, over = [], []
    for group, g in results.items():
        for ring, f in g["first_hour"].items():
            first.append({"group": group, "ring": ring, "events": g["events"], "lift": f["lift"], "lo": f["lo"],
                          "hi": f["hi"], "baseline_trips_per_event": g["trips_per_event_first_hour_baseline"][ring]})
        for ring, s in g["by_slot"].items():
            for i, minutes in enumerate(g["slots_minutes"]):
                over.append({"group": group, "ring": ring, "minutes_from_delay": minutes,
                             "lift": s["lift"][i], "lo": s["lo"][i], "hi": s["hi"][i]})
    return first, over


def incident_rows(incidents):
    """One row per agent incident, with the same checks agent/brief.py score uses."""
    rows = []
    for inc in incidents:
        f, usual = inc["facts"], inc["facts"].get("usual_length") or {}
        actual, median, bound = inc.get("actual_minutes"), usual.get("median_minutes"), usual.get("8_in_10_under_minutes")
        cleared = actual is not None
        rows.append({
            "alert_id": inc["alert_id"], "first_seen": inc["first_seen"], "cleared_at": inc.get("cleared_at"),
            "line": f.get("line"), "effect": f.get("effect"), "cause": f.get("cause"),
            "affected_stations": "; ".join(f.get("affected_stations") or []),
            "estimate_median_min": median, "estimate_8_in_10_under_min": bound, "actual_min": actual,
            "baseline_median_min": inc.get("baseline_median_minutes"),
            "abs_error_min": abs(actual - median) if cleared and median is not None else None,
            "baseline_abs_error_min": abs(actual - inc["baseline_median_minutes"])
            if cleared and inc.get("baseline_median_minutes") is not None else None,
            "within_bound": (actual <= bound) if cleared and bound is not None else None,
            "has_brief": bool(inc.get("brief")),
            "faithful": (not inc.get("unsupported_numbers")) if inc.get("brief") else None,
        })
    return rows


def write(name, rows):
    if not rows:
        raise SystemExit(f"{name}: no rows; refusing to write an empty extract")
    path = OUT / name
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)  # Tableau never sees a half-written file
    print(f"wrote {path.relative_to(ROOT)} ({len(rows):,} rows)")


def main():
    import duckdb
    OUT.mkdir(parents=True, exist_ok=True)
    first, over = finding_rows(json.loads(RESULTS.read_text()))
    write("finding_first_hour.csv", first)
    write("finding_over_time.csv", over)
    write("agent_incidents.csv", incident_rows(
        json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(INCIDENTS / "*.json")))))
    con = duckdb.connect(str(DB), read_only=True)
    for table, name in (("mart_delays_monthly", "delays_monthly.csv"), ("mart_dock_levels_hourly", "dock_levels_hourly.csv")):
        cur = con.execute(f"select * from {table}")
        cols = [d[0] for d in cur.description]
        write(name, [dict(zip(cols, r)) for r in cur.fetchall()])
    con.close()


if __name__ == "__main__":
    main()
