"""Write map/data.js for the pixel map: geometry plus a few real past disruptions.

Usage: .venv/bin/python map/export.py   (reads the warehouse and the GTFS zip, read-only)

Geometry is projected onto a 100 m pixel grid turned 17 degrees so the street grid
(Yonge St) runs straight up, the way Toronto maps are usually drawn.
  streets   every bus/streetcar route shape in the GTFS, rasterised (a city outline from our own data)
  lines     subway route shapes, one per line, in TTC colours
  stations  subway and Bike Share stations

Disruptions: the longest single delays from 2023 on (Lines 1/2/4, 7am-9pm, weather codes left out
because weather also changes cycling), each on its own day, with 10+ Bike Share stations within
1 km of the affected stretch. For each: trips started at those stations per 15-minute slot, 1 hour
before to 3 hours after, on the day and on normal days (same weekday and time, 1-4 weeks before and
after, skipping days with a 10+ min delay on the same line within 3 hours; at least 3 needed),
the method of analysis/disruption_effect.py without the citywide control.
"""
import base64
import csv
import io
import json
import math
import zipfile
from datetime import timedelta
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "warehouse" / "linedown.duckdb"
GTFS_DIR = ROOT / "data" / "raw" / "history" / "ttc-routes-and-schedules"
OUT = ROOT / "map" / "data.js"   # a script, not JSON, so index.html also opens straight from disk

CELL = 100                      # metres per map pixel
TURN = math.radians(-17)        # Toronto's street grid vs true north
LAT0, LON0 = 43.70, -79.40
K = list(range(-4, 12))         # 15-minute slots relative to the delay
CONTROL_DAYS = [-28, -21, -14, -7, 7, 14, 21, 28]
MIN_CONTROLS = 3
N_EVENTS = 8
MIN_NORMAL_TRIPS = 20       # over the whole 4-hour window
WEATHER = ("MUFM", "MUWEA", "PUSIS", "PUTIS")
LINE_NAMES = {"1": "Line 1 Yonge-University", "2": "Line 2 Bloor-Danforth", "4": "Line 4 Sheppard"}


def project(lat, lon):
    """Metres east/north of the origin, turned so Yonge St points up; returns unscaled (x, y) in metres, y down."""
    e = (lon - LON0) * 111320 * math.cos(math.radians(LAT0))
    n = (lat - LAT0) * 110540
    return e * math.cos(TURN) - n * math.sin(TURN), -(e * math.sin(TURN) + n * math.cos(TURN))


def shape_event(rows, control_days):
    """rows: (day_offset, k, station_id, trips). control_days: clean offsets usable as normal days.
    Returns per-station and total counts on the day, and the normal-day mean, low and high per slot."""
    days = [0] + list(control_days)
    stations = sorted({s for _, _, s, _ in rows})
    grid = {(d, k, s): 0 for d in days for k in K for s in stations}
    for d, k, s, n in rows:
        if (d, k, s) in grid:
            grid[(d, k, s)] += n
    totals = {d: [sum(grid[(d, k, s)] for s in stations) for k in K] for d in days}
    nc = len(control_days)
    return {
        "stations": stations,
        "actual": [[grid[(0, k, s)] for k in K] for s in stations],
        "normal": [[round(sum(grid[(d, k, s)] for d in control_days) / nc, 2) for k in K] for s in stations],
        "total_actual": totals[0],
        "total_normal": [round(sum(totals[d][i] for d in control_days) / nc, 2) for i in range(len(K))],
        "total_normal_low": [min(totals[d][i] for d in control_days) for i in range(len(K))],
        "total_normal_high": [max(totals[d][i] for d in control_days) for i in range(len(K))],
        "normal_days": nc,
    }


def raster(points, cells):
    """Add the 100 m cells a polyline passes through (points already in metres)."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0)) / (CELL / 2)))
        for i in range(steps + 1):
            cells.add((round((x0 + (x1 - x0) * i / steps) / CELL), round((y0 + (y1 - y0) * i / steps) / CELL)))


def read_gtfs():
    """Subway shapes (longest per line) and all other route shapes, as metre polylines."""
    gtfs = sorted(GTFS_DIR.glob("*/opendata_ttc_schedules.zip"))[-1]   # newest download
    with zipfile.ZipFile(gtfs) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"))
        routes = {r["route_id"]: r for r in rows("routes.txt")}
        shape_route = {t["shape_id"]: t["route_id"] for t in rows("trips.txt")}
        pts = {}
        for p in rows("shapes.txt"):
            if p["shape_id"] in shape_route:
                pts.setdefault(p["shape_id"], []).append((int(p["shape_pt_sequence"]), float(p["shape_pt_lat"]), float(p["shape_pt_lon"])))
    subway, other = {}, []
    for sid, p in pts.items():
        r = routes[shape_route[sid]]
        line = [project(lat, lon) for _, lat, lon in sorted(p)]
        if r["route_type"] == "1":
            if len(line) > len(subway.get(r["route_short_name"], ([], ""))[0]):
                subway[r["route_short_name"]] = (line, "#" + r["route_color"])
        else:
            other.append(line)
    return subway, other


def pick_events(con):
    """Yield the longest non-weather delays first, one per day, with their affected stations and clean normal days."""
    cands = con.execute(f"""
        with near as (
            select ds.delay_id, count(distinct b.station_id) as bikes
            from delay_stations ds join subway_stations ss using (station), bike_stations b
            where 2 * 6371000 * asin(sqrt(pow(sin(radians(b.lat - ss.lat) / 2), 2)
                  + cos(radians(ss.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - ss.lon) / 2), 2))) <= 1000
            group by ds.delay_id)
        select d.delay_id, d.occurred_at, d.line, d.station, d.station_to, d.min_delay, d.code, dc.description
        from subway_delays d join near using (delay_id) left join delay_codes dc using (code)
        where d.occurred_at >= '2023-01-01' and d.line in ('1', '2', '4') and d.station is not null
          and hour(d.occurred_at) between 7 and 20 and d.code not in {WEATHER} and near.bikes >= 10
        order by d.min_delay desc, d.occurred_at""").fetchall()
    last_trip = con.execute("select max(start_time) from trips").fetchone()[0]
    days_used = set()
    for delay_id, at, line, st, st_to, mins, code, desc in cands:
        if at.date() in days_used:
            continue
        t0 = at.replace(minute=at.minute - at.minute % 15, second=0)
        clean = [d for d in CONTROL_DAYS if t0 + timedelta(days=d, hours=3) <= last_trip and not con.execute(
            """select 1 from subway_delays where line = ? and min_delay >= 10
               and occurred_at between ? and ? limit 1""",
            [line, t0 + timedelta(days=d, hours=-3), t0 + timedelta(days=d, hours=3)]).fetchone()]
        if len(clean) < MIN_CONTROLS:
            continue
        stations = [s for (s,) in con.execute("select station from delay_stations where delay_id = ?", [delay_id]).fetchall()]
        days_used.add(at.date())
        yield dict(delay_id=delay_id, at=at, t0=t0, line=line, station=st, station_to=st_to,
                   min_delay=mins, code=code, cause=desc, affected=stations, control_days=clean)


def event_counts(con, ev):
    """(day_offset, k, station_id, trips) for bike stations within 1 km of the affected stations."""
    out = []
    near = con.execute("""
        select distinct b.station_id from bike_stations b, subway_stations ss
        where ss.station in (select unnest(?))
          and 2 * 6371000 * asin(sqrt(pow(sin(radians(b.lat - ss.lat) / 2), 2)
              + cos(radians(ss.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - ss.lon) / 2), 2))) <= 1000""",
        [ev["affected"]]).fetchall()
    ids = [s for (s,) in near]
    for d in [0] + ev["control_days"]:
        start = ev["t0"] + timedelta(days=d, minutes=15 * K[0])
        for k, s, n in con.execute(f"""
                select (datediff('minute', ?::timestamp, start_time) // 15)::int + {K[0]} as k, start_station_id, count(*)
                from trips where start_time >= ? and start_time < ? and start_station_id in (select unnest(?))
                group by all""", [start, start, start + timedelta(minutes=15 * len(K)), ids]).fetchall():
            out.append((d, k, s, n))
    return ids, out


def main():
    con = duckdb.connect(str(DB), read_only=True)
    subway, other = read_gtfs()
    cells = set()
    for line in other:
        raster(line, cells)

    stations = con.execute("select station, lat, lon, lines from subway_stations order by station").fetchall()
    bikes = con.execute("select station_id, name, lat, lon from bike_stations order by station_id").fetchall()
    sxy = {s: project(lat, lon) for s, lat, lon, _ in stations}
    bxy = {b: project(lat, lon) for b, _, lat, lon in bikes}
    # map frame: subway network plus 2 km
    xs = [x for x, _ in sxy.values()]
    ys = [y for _, y in sxy.values()]
    x0, y0 = min(xs) - 2000, min(ys) - 2000
    w, h = math.ceil((max(xs) + 2000 - x0) / CELL), math.ceil((max(ys) + 2000 - y0) / CELL)

    def px(xy):
        return [round((xy[0] - x0) / CELL, 1), round((xy[1] - y0) / CELL, 1)]

    bits = bytearray((w * h + 7) // 8)
    for cx, cy in cells:
        i, j = cx - round(x0 / CELL), cy - round(y0 / CELL)
        if 0 <= i < w and 0 <= j < h:
            bits[(j * w + i) // 8] |= 1 << ((j * w + i) % 8)

    events = []
    for ev in pick_events(con):
        ids, rows = event_counts(con, ev)
        shaped = shape_event(rows, ev["control_days"])
        if sum(shaped["total_normal"]) < MIN_NORMAL_TRIPS:   # bike stations too new or too quiet to show anything
            continue
        missing = sorted(set(ids) - set(shaped["stations"]))   # near but no trips at all in any window: show as zeros
        shaped["stations"] += missing
        shaped["actual"] += [[0] * len(K)] * len(missing)
        shaped["normal"] += [[0] * len(K)] * len(missing)
        events.append({
            "id": ev["delay_id"], "when": ev["at"].isoformat(timespec="minutes"),
            "slot0": ev["t0"].isoformat(timespec="minutes"), "line": ev["line"],
            "from": ev["station"], "to": ev["station_to"], "min_delay": ev["min_delay"],
            "code": ev["code"], "cause": ev["cause"], "affected": ev["affected"], **shaped,
        })
        print(f"{ev['at']:%Y-%m-%d %H:%M} line {ev['line']} {ev['station']} to {ev['station_to']}: {ev['min_delay']} min, "
              f"{len(shaped['stations'])} bike stations, {shaped['normal_days']} normal days, "
              f"first hour {sum(shaped['total_actual'][4:8])} trips vs {sum(shaped['total_normal'][4:8]):.1f} normal")
        if len(events) == N_EVENTS:
            break

    data = {
        "size": [w, h], "cell_m": CELL, "slot_minutes": [k * 15 for k in K],
        "streets": base64.b64encode(bytes(bits)).decode(),
        "lines": {name: {"name": LINE_NAMES.get(name, name), "color": c, "points": [px(p) for p in line[::3] + [line[-1]]]}
                  for name, (line, c) in sorted(subway.items())},
        "stations": [{"name": s, "lines": lines, "xy": px(sxy[s])} for s, _, _, lines in stations],
        "bikes": {str(b): {"name": name, "xy": px(bxy[b])} for b, name, _, _ in bikes},
        "events": events,
    }
    OUT.write_text("const DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {w}x{h} pixels, {len(events)} disruptions)")


if __name__ == "__main__":
    main()
