"""Rebuild the Line Down warehouse from data/raw with one command.

Usage:
    .venv/bin/python warehouse/build.py            build data/warehouse/linedown.duckdb
    .venv/bin/python warehouse/build.py --twice    build twice and fail unless identical

data/raw is only read. The history zips are unpacked to data/warehouse/build/ as
clean UTF-8 (deleted afterwards), loaded as all-text staging tables, then
warehouse/sql/*.sql runs in order to make the core tables, then the checks run.
The new database replaces the old one only if every step and check passed.
"""
import codecs
import io
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "warehouse"
DB = OUT / "linedown.duckdb"
WORK = OUT / "build"
SQL = Path(__file__).resolve().parent / "sql"
SEEDS = Path(__file__).resolve().parent / "seeds"

# normalised header -> standard column. Anything else in a trip file stops the build.
TRIP_COLUMNS = {
    "trip id": "trip_id",
    "trip duration seconds": "duration", "trip duration": "duration",
    "from station id": "start_id", "start station id": "start_id",
    "trip start time": "start_time", "start time": "start_time",
    "from station name": "start_name", "start station name": "start_name",
    "to station id": "end_id", "end station id": "end_id",
    "trip stop time": "end_time", "end time": "end_time",
    "to station name": "end_name", "end station name": "end_name",
    "bike id": "bike_id",
    "user type": "user_type",
    "bike model": "bike_model",
}
TRIP_STD = ["trip_id", "duration", "start_id", "start_time", "start_name",
            "end_id", "end_time", "end_name", "bike_id", "user_type", "bike_model"]
DELAY_STD = ["date", "time", "day", "station", "code", "min_delay", "min_gap", "bound", "line", "vehicle"]
DELAY_IGNORED = {"id"}  # the since-2025 CSV's portal row id


def norm_header(h):
    return re.sub(r"[\s_]+", " ", h.lower()).strip()


def column_map(headers, known, ignored=frozenset()):
    """Map file headers to standard names; raise on a header we have not seen before."""
    out = {}
    for h in headers:
        n = norm_header(h)
        if n in ignored or n == "":
            continue
        if n not in known:
            raise ValueError(f"unknown column {h!r}; add it to the column map if it is expected")
        out[known[n]] = h
    return out


def select_list(mapping, std):
    """SQL select list giving every standard column, null where the file lacks it."""
    def q(h):
        return '"' + h.replace('"', '""') + '"'
    return ", ".join(f"{q(mapping[c])} as {c}" if c in mapping else f"null as {c}" for c in std)


def trip_time_format(year, name):
    """Date format of a trip file, from SOURCES.md (checked by the parse-rate check)."""
    if year == 2017:
        quarter = re.search(r"Q(\d)", name).group(1)
        return {"1": "dmy", "2": "dmy", "3": "mdy", "4": "mdy2s"}[quarter]
    if 2018 <= year <= 2023:
        return "mdy"
    if year >= 2024:
        return "iso"
    raise ValueError(f"no time format known for {year} {name}")


def latest(dataset):
    """Newest download of each file in a history dataset: {file name: path}."""
    files = {}
    for p in sorted((RAW / "history" / dataset).glob("*/*")):  # date folders sort oldest first
        files[p.name] = p
    return files


def unpack_csvs(zf, dest_dir, prefix, found):
    """Write every CSV in zf (and in zips inside it) to dest_dir as UTF-8 without BOM.
    Office lock files (~$...) are skipped. Output names are ours, never the zip's paths."""
    for info in zf.infolist():
        base = Path(info.filename).name
        if base.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(zf.read(info))) as inner:
                unpack_csvs(inner, dest_dir, prefix, found)
        elif base.lower().endswith(".csv") and not base.startswith("~$"):
            data = zf.read(info)
            if data.startswith(codecs.BOM_UTF8):
                data = data[3:]
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                data = data.decode("cp1252").encode("utf-8")  # several 2021-2025 months
            dest = dest_dir / (prefix + "__" + re.sub(r"[^A-Za-z0-9._-]", "_", base))
            dest.write_bytes(data)
            found.append((dest, base))


def xlsx_sheets(path):
    with zipfile.ZipFile(path) as z:
        return re.findall(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8"))


def lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def headers_of(con, rel):
    return [d[0] for d in con.execute(f"select * from {rel} limit 0").description]


def load_trips(con):
    con.execute(f"create table stg_trips (source_file varchar, year integer, time_format varchar, "
                f"{', '.join(c + ' varchar' for c in TRIP_STD)})")
    files = latest("bike-share-toronto-ridership-data")
    dest = WORK / "trips"
    dest.mkdir(parents=True)

    xlsx = files["bikeshare-ridership-2016.xlsx"]
    for sheet in xlsx_sheets(xlsx):
        rel = f"read_xlsx({lit(xlsx)}, sheet={lit(sheet)}, all_varchar=true)"
        fmt = "excel" if "Q3" in sheet else "dmy_or_swapped_excel"
        cols = select_list(column_map(headers_of(con, rel), TRIP_COLUMNS), TRIP_STD)
        con.execute(f"insert into stg_trips select {lit('2016.xlsx/' + sheet.strip())}, 2016, {lit(fmt)}, {cols} from {rel}")

    for name, path in sorted(files.items()):
        m = re.fullmatch(r"bikeshare-ridership-(\d{4})\.zip", name)
        if not m:
            continue  # readme, 2014-2015 aggregates, 2016 xlsx above
        year = int(m.group(1))
        found = []
        with zipfile.ZipFile(path) as z:
            unpack_csvs(z, dest, str(year), found)
        for csv_path, inner in sorted(found):
            rel = f"read_csv({lit(csv_path)}, all_varchar=true, header=true, store_rejects=true)"
            cols = select_list(column_map(headers_of(con, rel), TRIP_COLUMNS), TRIP_STD)
            fmt = trip_time_format(year, inner)
            con.execute(f"insert into stg_trips select {lit(f'{year}.zip/{inner}')}, {year}, {lit(fmt)}, {cols} from {rel}")


def load_delays(con):
    con.execute(f"create table stg_delays (source_file varchar, {', '.join(c + ' varchar' for c in DELAY_STD)})")
    known = {c.replace("_", " "): c for c in DELAY_STD}
    files = latest("ttc-subway-delay-data")
    for name, path in sorted(files.items()):
        if name.endswith(".xlsx") and re.search(r"\d{4}", name) and "codes" not in name:
            rels = [(f"{name}/{s.strip()}", f"read_xlsx({lit(path)}, sheet={lit(s)}, all_varchar=true)")
                    for s in xlsx_sheets(path)]
        elif name.endswith(".csv") and "since" in name:
            rels = [(name, f"read_csv({lit(path)}, all_varchar=true, header=true, store_rejects=true)")]
        else:
            continue
        for source, rel in rels:
            cols = select_list(column_map(headers_of(con, rel), known, DELAY_IGNORED), DELAY_STD)
            con.execute(f"insert into stg_delays select {lit(source)}, {cols} from {rel}")
    codes = files["code-descriptions.csv"]
    con.execute(f"create table stg_delay_codes as select * from read_csv({lit(codes)}, all_varchar=true, header=true)")


def load_gtfs(con):
    path = next(p for n, p in latest("ttc-routes-and-schedules").items() if n.endswith(".zip"))
    dest = WORK / "gtfs"
    dest.mkdir(parents=True)
    with zipfile.ZipFile(path) as z:
        for t in ("routes", "trips", "stop_times", "stops"):
            (dest / f"{t}.txt").write_bytes(z.read(f"{t}.txt"))
            con.execute(f"create table gtfs_{t} as select * from read_csv({lit(dest / (t + '.txt'))}, all_varchar=true, header=true)")


def load_live(con, cutoff):
    """Live snapshots up to cutoff (unix seconds, from the file name) so a build is repeatable
    while the collectors keep writing."""
    infos = [p for p in sorted((RAW / "bikeshare" / "station_information").glob("*/*.json.gz"))
             if int(p.name.split(".")[0]) <= cutoff]
    if not infos:
        raise RuntimeError("no station_information snapshot yet: is the collector running?")
    con.execute(f"create table bike_station_info as select * from read_json({lit(infos[-1])})")
    ts = "cast(regexp_extract(filename, '(\\d+)\\.json\\.gz$', 1) as bigint)"
    status = RAW / "bikeshare" / "station_status" / "*" / "*.json.gz"
    # shortcut: rescans every snapshot on each build; make it incremental once builds get slow.
    con.execute(f"""create table live_station_status as select last_updated, data
        from read_json({lit(status)}, union_by_name=true, filename=true) where {ts} <= {cutoff}""")
    alerts = RAW / "ttc" / "live_alerts" / "*" / "*.json.gz"
    con.execute(f"""create table live_ttc_alerts as select {ts} as snapshot_ts, routes
        from read_json({lit(alerts)}, union_by_name=true, filename=true) where {ts} <= {cutoff}""")
    con.execute(f"create table seed_station_aliases as select key, station from read_csv({lit(SEEDS / 'station_aliases.csv')}, header=true)")


def checks(con):
    """Print the build report; return a list of failures (empty means pass)."""
    fails = []
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731

    rejected = q("select s.file_path, count(*) from reject_errors e join reject_scans s using (scan_id) group by 1 order by 1")
    for f, n in rejected:
        print(f"  rejected rows (malformed CSV): {n:>7,}  {Path(f).name}")

    print("\ntrips per source file: kept / staged (unparseable times dropped)")
    for src, staged, kept in q("""
        select s.source_file, s.n, coalesce(t.n, 0) from
        (select source_file, count(*) n from stg_trips group by 1) s
        left join (select source_file, count(*) n from trips group by 1) t using (source_file)
        order by 1"""):
        flag = "" if kept >= staged * 0.999 else "   <-- FAIL: over 0.1% dropped"
        if flag:
            fails.append(f"{src}: {staged - kept} of {staged} trips had unparseable times")
        if flag or staged != kept:
            print(f"  {src:<55} {kept:>10,} / {staged:>10,}{flag}")

    years = dict(q("select year(start_time), count(*) from trips group by 1 order by 1"))
    print("\ntrips per year:", ", ".join(f"{y}: {n:,}" for y, n in years.items()))
    missing = [y for y in range(2016, 2027) if years.get(y, 0) < 100_000]
    if missing:
        fails.append(f"years with under 100k trips: {missing}")
    outside = sum(n for y, n in years.items() if not 2016 <= y <= 2026)
    if outside:
        fails.append(f"{outside} trips dated outside 2016-2026")

    (n, neg, no_start, from_name, unknown, dup) = q("""
        select count(*),
               count(*) filter (where end_time < start_time),
               count(*) filter (where start_station_id is null),
               count(*) filter (where start_id_from_name),
               count(*) filter (where start_station_id not in (select station_id from bike_stations)),
               count(*) - count(distinct trip_id)
        from trips""")[0]
    print(f"\ntrips: {n:,} | end before start: {neg:,} | no start station: {no_start:,} | "
          f"start id filled from name: {from_name:,} | start station not in today's station list: {unknown:,} | "
          f"duplicate trip ids: {dup:,}")
    if neg > n * 0.001:
        fails.append(f"{neg} trips end before they start (over 0.1%)")

    (dn, dmatched, dstaged) = q("""select count(*), count(station), (select count(*) from stg_delays) from subway_delays""")[0]
    print(f"\nsubway_delays: {dn:,} of {dstaged:,} staged | matched to a station: {dmatched:,} ({dmatched / dn:.1%})")
    if dn < dstaged * 0.999:
        fails.append(f"{dstaged - dn} delays had unparseable date/time")
    print("  most common unmatched station texts:")
    for raw, k in q("select station_raw, count(*) from subway_delays where station is null group by 1 order by 2 desc, 1 limit 12"):
        print(f"    {k:>6,}  {raw}")

    for t in ("subway_stations", "bike_stations", "delay_codes", "dock_snapshots", "dock_status", "ttc_alerts"):
        print(f"{t}: {q(f'select count(*) from {t}')[0][0]:,} rows")
    if q("select count(*) from subway_stations")[0][0] != 70:
        fails.append("expected 70 subway stations from GTFS")
    return fails


CORE = ["trips", "subway_delays", "delay_codes", "subway_stations", "subway_platforms",
        "bike_stations", "dock_snapshots", "dock_status", "ttc_alerts"]


def fingerprint(con):
    """Row count and order-independent content hash per core table."""
    return {t: con.execute(f"select count(*), sum(hash(x)::hugeint) from {t} x").fetchone() for t in CORE}


def build(cutoff):
    started = time.time()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    tmp = OUT / "linedown.duckdb.tmp"
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        con.execute("load excel")
        for step in (load_trips, load_delays, load_gtfs, load_live):
            print(f"[{time.time() - started:5.0f}s] {step.__name__}", flush=True)
            step(con, cutoff) if step is load_live else step(con)
        for f in sorted(SQL.glob("*.sql")):
            print(f"[{time.time() - started:5.0f}s] {f.name}", flush=True)
            con.execute(f.read_text())
        fails = checks(con)
        if fails:
            raise RuntimeError("checks failed:\n  " + "\n  ".join(fails))
        for t in ("stg_trips", "stg_delays", "stg_delay_codes", "gtfs_routes", "gtfs_trips", "gtfs_stop_times",
                  "gtfs_stops", "bike_station_info", "live_station_status", "live_ttc_alerts"):
            con.execute(f"drop table {t}")  # staging copies of raw are not part of the warehouse
        fp = fingerprint(con)
        con.close()
    except BaseException:
        con.close()
        tmp.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    os.replace(tmp, DB)
    print(f"\nbuilt {DB.relative_to(ROOT)} in {time.time() - started:.0f}s")
    return fp


if __name__ == "__main__":
    cutoff = int(time.time())
    first = build(cutoff)
    if "--twice" in sys.argv:
        second = build(cutoff)
        diff = [t for t in CORE if first[t] != second[t]]
        if diff:
            sys.exit(f"REBUILD DIFFERS for {diff}")
        print("rebuild identical:", ", ".join(f"{t} {first[t][0]:,}" for t in CORE))
