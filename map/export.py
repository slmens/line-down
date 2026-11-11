"""Write map/data.js for the map: geometry plus a few real past disruptions.

Usage: .venv/bin/python map/export.py   (reads the warehouse and the GTFS zip, read-only)

Coordinates are in units of 100 m, turned 17 degrees so the street grid (Yonge St) runs straight
up, the way Toronto maps are usually drawn.
  shore     Lake Ontario's shoreline, traced as the southern edge of all bus/streetcar route shapes
            in the GTFS (our own data, no map tiles), smoothed
  lines     subway route shapes, one per line, in TTC colours
  stations  subway and Bike Share stations

Disruptions: the longest single delays from 2023 on (Lines 1/2/4, 7am-9pm, weather codes left out
because weather also changes cycling), each on its own day, with 10+ Bike Share stations within
1 km of the affected stretch. For each: trips started at those stations per 15-minute slot, 1 hour
before to 3 hours after, on the day and on normal days (same weekday and time, 1-4 weeks before and
after, skipping days with a 10+ min delay on the same line within 3 hours; at least 3 needed),
the method of analysis/disruption_effect.py without the citywide control.

Replay: every trip starting within 2.5 km of the affected stations in that window, on the day and on
one normal day shown beside it. That day is picked by a fixed rule (pick_normal_day), never by how it looks.
"""
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

CELL = 100                      # metres per map unit
TURN = math.radians(-17)        # Toronto's street grid vs true north
LAT0, LON0 = 43.70, -79.40
K = list(range(-4, 12))         # 15-minute slots relative to the delay
CONTROL_DAYS = [-28, -21, -14, -7, 7, 14, 21, 28]
MIN_CONTROLS = 3
N_EVENTS = 8
MIN_NORMAL_TRIPS = 20       # over the whole 4-hour window
VIEW_M = 2500               # trips starting this close to an affected station are replayed
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


def pick_normal_day(day_totals):
    """day_totals: {day_offset: trips within 1 km}. The normal day closest to the average of all of them;
    ties go to the nearest week, then the earlier one. Fixed in advance so the shown day is not cherry-picked."""
    mean = sum(day_totals.values()) / len(day_totals)
    return min(day_totals, key=lambda d: (abs(day_totals[d] - mean), abs(d), d))


def shoreline(cells, w, window=9):
    """cells: occupied (x, y) map cells. Per column, the row just south of the southernmost cell,
    smoothed by a moving average; columns with nothing stay open (None)."""
    south = [None] * w
    for x, y in cells:
        if 0 <= x < w and (south[x] is None or y + 1 > south[x]):
            south[x] = y + 1
    out = []
    for x in range(w):
        near = [v for v in south[max(0, x - window // 2):x + window // 2 + 1] if v is not None]
        out.append([x, round(sum(near) / len(near), 1)] if near else None)
    return [p for p in out if p]


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
    ids = sorted(s for (s,) in near)
    for d in [0] + ev["control_days"]:
        start = ev["t0"] + timedelta(days=d, minutes=15 * K[0])
        for k, s, n in con.execute(f"""
                select (datediff('minute', ?::timestamp, start_time) // 15)::int + {K[0]} as k, start_station_id, count(*)
                from trips where start_time >= ? and start_time < ? and start_station_id in (select unnest(?))
                group by all""", [start, start, start + timedelta(minutes=15 * len(K)), ids]).fetchall():
            out.append((d, k, s, n))
    return ids, out


def within(con, stations, metres):
    return [s for (s,) in con.execute("""
        select distinct b.station_id from bike_stations b, subway_stations ss
        where ss.station in (select unnest(?))
          and 2 * 6371000 * asin(sqrt(pow(sin(radians(b.lat - ss.lat) / 2), 2)
              + cos(radians(ss.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - ss.lon) / 2), 2))) <= ?""",
        [stations, metres]).fetchall()]


def day_trips(con, ev, d, view_ids, near_ids):
    """[seconds after window start, duration s, start id, end id or None, 1 if it started within 1 km]."""
    start = ev["t0"] + timedelta(days=d, minutes=15 * K[0])
    near = set(near_ids)
    return [[t, dur, s, e, int(s in near)] for t, dur, s, e in con.execute("""
        select datediff('second', ?::timestamp, start_time), duration_s, start_station_id, end_station_id
        from trips where start_time >= ? and start_time < ? and start_station_id in (select unnest(?))
        order by start_time""", [start, start, start + timedelta(minutes=15 * len(K)), view_ids]).fetchall()]


def first_hour(con, ev, d, near_ids):
    """Trips started within 1 km in the hour after the delay was logged, d days away."""
    at = ev["at"] + timedelta(days=d)
    return con.execute("""select count(*) from trips where start_time >= ? and start_time < ?
                          and start_station_id in (select unnest(?))""", [at, at + timedelta(hours=1), near_ids]).fetchone()[0]


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

    shore = shoreline({(cx - round(x0 / CELL), cy - round(y0 / CELL)) for cx, cy in cells}, w)
    ends = {line: [a, b] for line, a, b in con.execute(
        "select line, arg_min(station, seq), arg_max(station, seq) from line_stations group by line").fetchall()}

    events = []
    for ev in pick_events(con):
        ids, rows = event_counts(con, ev)
        shaped = shape_event(rows, ev["control_days"])
        if sum(shaped["total_normal"]) < MIN_NORMAL_TRIPS:   # bike stations too new or too quiet to show anything
            continue
        for key in ("stations", "actual", "normal"):   # per-station detail is not shown any more
            del shaped[key]
        totals = {d: sum(n for dd, _, _, n in rows if dd == d) for d in ev["control_days"]}
        nd = pick_normal_day(totals)
        view = within(con, ev["affected"], VIEW_M)
        events.append({
            "id": ev["delay_id"], "when": ev["at"].isoformat(timespec="minutes"),
            "slot0": ev["t0"].isoformat(timespec="minutes"), "line": ev["line"],
            "from": ev["station"], "to": ev["station_to"], "min_delay": ev["min_delay"],
            "code": ev["code"], "cause": ev["cause"], "affected": ev["affected"], "near": ids, **shaped,
            "normal_offset": nd, "normal_date": (ev["at"] + timedelta(days=nd)).date().isoformat(),
            "first_hour": first_hour(con, ev, 0, ids),
            "first_hour_normal": {str(d): first_hour(con, ev, d, ids) for d in ev["control_days"]},
            "trips": day_trips(con, ev, 0, view, ids), "trips_normal": day_trips(con, ev, nd, view, ids),
        })
        print(f"{ev['at']:%Y-%m-%d %H:%M} line {ev['line']} {ev['station']} to {ev['station_to']}: {ev['min_delay']} min, "
              f"{len(ids)} bike stations, {shaped['normal_days']} normal days, first hour after {events[-1]['first_hour']} trips, "
              f"shown normal day {events[-1]['normal_date']} {events[-1]['first_hour_normal'][str(nd)]}, "
              f"all normal days {sorted(events[-1]['first_hour_normal'].values())}")
        if len(events) == N_EVENTS:
            break

    data = {
        "size": [w, h], "cell_m": CELL, "slot_minutes": [k * 15 for k in K],
        "shore": shore,
        "lines": {name: {"name": LINE_NAMES.get(name, name), "color": c, "ends": ends.get(name, []),
                         "points": [px(p) for p in line[::2] + [line[-1]]]}
                  for name, (line, c) in sorted(subway.items())},
        "stations": [{"name": s, "lines": lines, "xy": px(sxy[s])} for s, _, _, lines in stations],
        "bikes": {str(b): {"name": name, "xy": px(bxy[b])} for b, name, _, _ in bikes},
        "events": events,
    }
    OUT.write_text("const DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {w}x{h} cells of 100 m, {len(events)} disruptions)")


if __name__ == "__main__":
    main()
