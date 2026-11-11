"""Stuck at a subway station during a delay: wait, walk, or take a Bike Share bike?

Usage:
    .venv/bin/python models/walk_or_wait.py                  score the rule on 2022
    .venv/bin/python models/walk_or_wait.py "St Andrew Station" "Union Station" SUUT 10
        advice for a rider at St Andrew heading toward Union, delay code SUUT, 10 min in

Goal: reach the next station in your direction (where trains are assumed to run).
  wait  = remaining delay + train ride. Remaining delay comes from the TTC delay log:
          for past delays with this cause that had already lasted `elapsed` minutes, how
          much longer they ran (min_delay - elapsed).
  bike  = leave station + walk to nearest dock + RIDE + walk to the target + enter station.
          RIDE is the median of real Bike Share trips between those two docks when there
          are at least MIN_TRIPS of them; otherwise distance at 15 km/h. Assumes a bike
          and a free dock are there (no live dock check yet).
  walk  = leave station + walk to the target.
Walking parts use straight-line distance x1.3 at 4.8 km/h. Leave if waiting was slower
in more than half of the past cases.

Scoring: the rule is built from 2014-2021 (delays and bike trips) and tested on 2022
delays, where waiting costs what the 2022 delay really lasted and biking costs the 2022
median ride on that route. (2023-2024 were used for an earlier version, 2025-2026 for
the delay-length model.)
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "warehouse" / "linedown.duckdb"
OUT = Path(__file__).resolve().parent / "output"

WALK_M_PER_MIN = 80      # 4.8 km/h
BIKE_M_PER_MIN = 250     # 15 km/h, only where there are too few real trips
DETOUR = 1.3             # streets vs straight line, for walking (and the bike fallback)
TRAIN_MIN_PER_STOP = 2.0  # shortcut: flat; GTFS stop_times could give real run times
LEAVE_STATION = 3.0      # platform to street (and unlocking a bike)
ENTER_STATION = 2.0      # dock/street to platform
MIN_SAMPLES = 30         # fewer past delays for a cause -> use all causes
MIN_TRIPS = 20           # fewer real trips between two docks -> use distance and speed
TRAIN_UNTIL, TEST_YEAR = 2021, 2022
ADVICE_TRIPS_FROM = "2024-01-01"  # recent rides for live advice

HAVERSINE = """2 * 6371000 * asin(sqrt(pow(sin(radians({b}.lat - {a}.lat) / 2), 2)
    + cos(radians({a}.lat)) * cos(radians({b}.lat)) * pow(sin(radians({b}.lon - {a}.lon) / 2), 2)))"""

# Each station and its neighbours on each line, with distances and nearest docks.
LEGS = f"""
with nearest_dock as (
    select s.station, arg_min(b.station_id, d) as dock_id, min(d) as dock_m
    from (select s.station, b.station_id, {HAVERSINE.format(a='s', b='b')} as d
          from subway_stations s, bike_stations b) x
    join subway_stations s using (station) join bike_stations b using (station_id)
    group by s.station
)
select a.line, a.station as here, t.station as target,
       {HAVERSINE.format(a='sa', b='st')} as here_to_target_m,
       da.dock_m as here_dock_m, dt.dock_m as target_dock_m,
       {HAVERSINE.format(a='ba', b='bt')} as dock_to_dock_m,
       da.dock_id, dt.dock_id
from line_stations a
join line_stations t on t.line = a.line and abs(t.seq - a.seq) = 1
join subway_stations sa on sa.station = a.station
join subway_stations st on st.station = t.station
join nearest_dock da on da.station = a.station
join nearest_dock dt on dt.station = t.station
join bike_stations ba on ba.station_id = da.dock_id
join bike_stations bt on bt.station_id = dt.dock_id
"""


def ride_times(con, legs, start, end):
    """Median real ride minutes between each leg's two docks, trips in [start, end)."""
    pairs = sorted({(leg[7], leg[8]) for leg in legs})
    con.execute("create or replace temp table pairs(a integer, b integer)")
    con.executemany("insert into pairs values (?, ?)", pairs)
    rows = con.execute(f"""
        select p.a, p.b, median(t.duration_s) / 60.0, count(*)
        from pairs p join trips t on t.start_station_id = p.a and t.end_station_id = p.b
        where t.start_time >= '{start}' and t.start_time < '{end}' and t.duration_s between 60 and 3600
        group by all having count(*) >= {MIN_TRIPS}""").fetchall()
    return {(a, b): (float(m), n) for a, b, m, n in rows}


def option_minutes(leg, rides):
    """(bike minutes, walk minutes, ride was measured?) for one leg."""
    here_to_target, here_dock, target_dock, dock_to_dock, dock_a, dock_b = leg[3:9]
    measured = rides.get((dock_a, dock_b))
    ride = measured[0] if measured else dock_to_dock * DETOUR / BIKE_M_PER_MIN
    bike = (LEAVE_STATION + here_dock * DETOUR / WALK_M_PER_MIN + ride
            + target_dock * DETOUR / WALK_M_PER_MIN + ENTER_STATION)
    walk = LEAVE_STATION + here_to_target * DETOUR / WALK_M_PER_MIN + ENTER_STATION
    return bike, walk, measured is not None


def remaining_samples(history, code, elapsed):
    """Minutes left for past delays of this cause that had lasted `elapsed` minutes."""
    lengths = history.get(code, np.array([]))
    left = lengths[lengths >= elapsed] - elapsed
    if len(left) < MIN_SAMPLES:
        everything = np.concatenate(list(history.values()))
        left = everything[everything >= elapsed] - elapsed
    return left


def decide(left, bike, walk):
    """Return (choice, P(waiting is slower than the best alternative), wait median)."""
    wait = left + TRAIN_MIN_PER_STOP
    alt_name, alt = ("bike", bike) if bike < walk else ("walk", walk)
    p_slower = float(np.mean(wait > alt))
    return (alt_name if p_slower > 0.5 else "wait"), p_slower, float(np.median(wait))


def load_history(con, years_sql):
    rows = con.execute(f"""select coalesce(code, 'NONE'), min_delay from subway_delays
        where line in ('1', '2', '4') and min_delay > 0 and {years_sql}""").fetchall()
    history = {}
    for code, m in rows:
        history.setdefault(code, []).append(m)
    return {c: np.array(v, dtype=float) for c, v in history.items()}


def evaluate(con, legs, rides_known, rides_real, elapsed):
    history = load_history(con, f"year(occurred_at) <= {TRAIN_UNTIL}")
    by_station = {}
    for leg in legs:
        by_station.setdefault((leg[0], leg[1]), []).append(leg)
    cases = con.execute(f"""select line, station, coalesce(code, 'NONE'), min_delay from subway_delays
        where line in ('1', '2', '4') and station is not null and station_to is null
          and min_delay >= {elapsed} and year(occurred_at) = {TEST_YEAR}""").fetchall()
    totals = {k: [] for k in ("rule", "always wait", "always bike", "always walk", "best possible")}
    choices = {"wait": 0, "bike": 0, "walk": 0}
    for line, station, code, length in cases:
        left = remaining_samples(history, code, elapsed)
        for leg in by_station.get((line, station), []):  # one rider each way
            bike_est, walk, _ = option_minutes(leg, rides_known)      # what the rule believed
            bike_real, _, _ = option_minutes(leg, rides_real)         # what 2022 riders took
            choice, _, _ = decide(left, bike_est, walk)
            choices[choice] += 1
            actual = {"wait": (length - elapsed) + TRAIN_MIN_PER_STOP, "bike": bike_real, "walk": walk}
            totals["rule"].append(actual[choice])
            totals["always wait"].append(actual["wait"])
            totals["always bike"].append(actual["bike"])
            totals["always walk"].append(actual["walk"])
            totals["best possible"].append(min(actual.values()))
    rule = np.array(totals["rule"])
    rng = np.random.default_rng(20261111)
    result = {"elapsed_minutes": elapsed, "riders": len(rule), "rule_choices": choices,
              "mean_minutes_to_next_station": {k: round(float(np.mean(v)), 2) for k, v in totals.items()}}
    for base in ("always wait", "always bike", "always walk"):
        diff = np.array(totals[base]) - rule
        idx = rng.integers(0, len(diff), size=(1000, len(diff)))
        result[f"rule_saves_vs_{base.replace(' ', '_')}"] = {
            "minutes": round(float(diff.mean()), 2),
            "range_95": [round(float(x), 2) for x in np.percentile(diff[idx].mean(axis=1), [2.5, 97.5])]}
    return result


def advise(con, here, toward, code, elapsed):
    """Plain-language advice for one rider, using all delay history and recent rides."""
    legs = con.execute(LEGS).fetchall()
    leg = next((l for l in legs if l[1] == here and l[2] == toward), None)
    if leg is None:
        return f"{here} -> {toward} is not a pair of neighbouring stations on one line."
    rides = ride_times(con, [leg], ADVICE_TRIPS_FROM, "2100-01-01")
    bike, walk, measured = option_minutes(leg, rides)
    left = remaining_samples(load_history(con, "true"), code, elapsed)
    choice, p, wait_med = decide(left, bike, walk)
    p80 = float(np.percentile(left + TRAIN_MIN_PER_STOP, 80))
    alt = "bike" if bike < walk else "walk"
    if 0.4 <= p <= 0.6:
        head = f"About even: the {alt} beats waiting in {p:.0%} of past cases."
    elif choice == "wait":
        head = f"Wait: waiting was faster in {1 - p:.0%} of past cases."
    else:
        head = f"{'Take a bike' if alt == 'bike' else 'Walk'}: faster than waiting in {p:.0%} of past cases."
    ride_note = (f"real median ride {rides[(leg[7], leg[8])][0]:.1f} min over {rides[(leg[7], leg[8])][1]:,} trips"
                 if measured else f"no ride history, estimated at 15 km/h")
    return (f"{head}\n"
            f"  Wait: about {wait_med:.0f} min to reach {toward} (8 in 10 times under {p80:.0f}), "
            f"based on {len(left):,} past '{code}' delays that lasted {elapsed}+ min.\n"
            f"  Bike: {bike:.0f} min. Dock {leg[4]:.0f} m away, {ride_note}, dock {leg[5]:.0f} m from {toward}. "
            f"Assumes a bike is there.\n"
            f"  Walk: {walk:.0f} min ({leg[3] * DETOUR / 1000:.1f} km).")


def main(argv):
    con = duckdb.connect(str(DB), read_only=True)
    if len(argv) == 5:
        print(advise(con, argv[1], argv[2], argv[3], int(argv[4])))
        return
    legs = con.execute(LEGS).fetchall()
    rides_known = ride_times(con, legs, "2017-01-01", f"{TRAIN_UNTIL + 1}-01-01")
    rides_real = ride_times(con, legs, f"{TEST_YEAR}-01-01", f"{TEST_YEAR + 1}-01-01")
    coverage = {"legs": len(legs), "legs_with_real_ride_times_2017_2021": sum((l[7], l[8]) in rides_known for l in legs),
                "legs_with_real_ride_times_2022": sum((l[7], l[8]) in rides_real for l in legs)}
    results = {"coverage": coverage, "by_elapsed": [evaluate(con, legs, rides_known, rides_real, e) for e in (5, 10, 15)]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "walk_or_wait_metrics.json").write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main(sys.argv)
