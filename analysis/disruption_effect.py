"""Does a subway disruption push people onto Bike Share nearby? How far, how long?

Usage: .venv/bin/python analysis/disruption_effect.py

Design (difference-in-differences event study), read from the warehouse:
  events   10+ minute delays on Lines 1/2/4 with a station, 2023-02 to 2026-08, 6am-11pm.
           Delays on the same line less than 30 minutes apart are one event.
  rings    Bike stations 0-250 m, 250-500 m, 500-1000 m from any affected subway station.
  slots    15-minute slots from 1 hour before to 3 hours after the event.
  baseline The same slots 1-4 weeks before and after (same weekday and time), skipping
           days with a disruption on the same line within 3 hours.
  control  Stations more than 2 km from every affected subway station, same slots,
           to cancel out citywide swings (weather, holidays, events).
  lift     (near / near baseline) / (far / far baseline) - 1, summed over events.
  range    95% bootstrap interval, resampling events (1000 draws, fixed seed).
  placebo  The same pipeline on fake events: each real event moved 5-9 weeks to a time
           with no disruption on that line. Should show about zero.

Writes analysis/output/results.json; prints a summary.
"""
import json
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "warehouse" / "linedown.duckdb"
OUT = ROOT / "analysis" / "output"
RINGS = ["0-250 m", "250-500 m", "500-1000 m"]
K = list(range(-4, 12))            # 15-minute slots relative to the event
CONTROL_DAYS = [-28, -21, -14, -7, 7, 14, 21, 28]
MIN_CONTROLS = 3
B = 1000
SEED = 20261111

SETUP = """
create temp table t15 as
select start_station_id as s, time_bucket(interval 15 minute, start_time) as slot, count(*) as n
from trips where start_time >= '2022-12-01' and start_station_id is not null group by all;

create temp table city15 as select slot, sum(n) as n from t15 group by slot;

-- subway station -> bike stations within 2 km (haversine, metres)
create temp table near_bike as
select * from (
    select ss.station, b.station_id,
           2 * 6371000 * asin(sqrt(pow(sin(radians(b.lat - ss.lat) / 2), 2)
               + cos(radians(ss.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - ss.lon) / 2), 2))) as d
    from subway_stations ss, bike_stations b
) where d <= 2000;

-- real events: cluster qualifying delays per line, new event after a 30+ minute gap
create temp table qualifying as
select delay_id, line, occurred_at, min_delay from subway_delays
where min_delay >= 10 and line in ('1', '2', '4') and station is not null
  and occurred_at >= '2023-02-01' and occurred_at < '2026-09-01'
  and hour(occurred_at) between 6 and 22;

create temp table delay_event as
select delay_id, line, occurred_at, min_delay,
       sum(new) over (order by line, occurred_at, delay_id rows unbounded preceding) as e
from (select *, coalesce(occurred_at - lag(occurred_at) over (partition by line order by occurred_at, delay_id)
                         > interval 30 minute, true)::int as new
      from qualifying);

create temp table real_ev as
select e, any_value(line) as line, time_bucket(interval 15 minute, min(occurred_at)) as t0,
       max(min_delay) as max_delay
from delay_event group by e;

create temp table real_ev_st as
select distinct de.e, ds.station from delay_event de join delay_stations ds using (delay_id);
"""

COUNTS = """
create or replace temp table ev_ring as
select e.e, nb.station_id, min(nb.d) as d from {st} e join near_bike nb using (station) group by all;

create or replace temp table grid as
select ev.e, dd.d, k.k, ev.t0 + to_days(dd.d) + to_minutes(k.k * 15) as slot
from {ev} ev, (select unnest({days}) as d) dd, (select unnest({ks}) as k) k
where dd.d = 0 or (
    ev.t0 + to_days(dd.d) + interval 3 hour <= timestamp '2026-09-30 23:00'
    and not exists (select 1 from real_ev x where x.line = ev.line
                    and x.t0 between ev.t0 + to_days(dd.d) - interval 3 hour
                                 and ev.t0 + to_days(dd.d) + interval 3 hour));

create or replace temp table ring_counts as
select g.e, g.d, g.k,
       sum(t.n) filter (where r.d < 250) as r0,
       sum(t.n) filter (where r.d >= 250 and r.d < 500) as r1,
       sum(t.n) filter (where r.d >= 500 and r.d < 1000) as r2,
       sum(t.n) as within2k
from grid g join ev_ring r using (e) join t15 t on t.s = r.station_id and t.slot = g.slot
group by all;
"""

RESULT = """
select g.e, g.d, g.k, coalesce(rc.r0, 0), coalesce(rc.r1, 0), coalesce(rc.r2, 0),
       coalesce(c.n, 0) - coalesce(rc.within2k, 0) as far
from grid g
left join ring_counts rc using (e, d, k)
left join city15 c on c.slot = g.slot
order by g.e, g.d, g.k
"""


def per_event(con, ev, st):
    """Arrays for events with enough clean control days: event counts and baseline means."""
    con.execute(COUNTS.format(ev=ev, st=st, days=[0] + CONTROL_DAYS, ks=K))
    rows = con.execute(RESULT).fetchall()
    data = {}
    for e, d, k, r0, r1, r2, far in rows:
        data.setdefault(e, {}).setdefault(d, {})[k] = (r0, r1, r2, far)
    events, ev_counts, base = [], [], []
    for e, days in data.items():
        controls = [d for d in days if d != 0 and len(days[d]) == len(K)]
        if 0 not in days or len(controls) < MIN_CONTROLS:
            continue
        ev_counts.append([days[0][k] for k in K])
        base.append(np.mean([[days[d][k] for k in K] for d in controls], axis=0))
        events.append(e)
    return events, np.array(ev_counts, dtype=float), np.array(base, dtype=float)  # [E, K, 4]


def lift(ev_counts, base, w=None):
    """lift[ring, k] = (near_ev/near_base) / (far_ev/far_base) - 1, events weighted by w."""
    w = np.ones(len(ev_counts)) if w is None else w
    ev_sum = np.tensordot(w, ev_counts, axes=1)   # [K, 4]
    base_sum = np.tensordot(w, base, axes=1)
    ratio = ev_sum / base_sum
    return (ratio[:, :3] / ratio[:, 3:4]).T - 1   # [3 rings, K]


def summarise(ev_counts, base, rng):
    point = lift(ev_counts, base)
    draws = np.array([lift(ev_counts, base, rng.multinomial(len(ev_counts), np.full(len(ev_counts), 1 / len(ev_counts))))
                      for _ in range(B)])
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
    first_hour = slice(K.index(0), K.index(4))     # slots 0..3: the hour after the event starts
    w_point = lift_window(ev_counts, base, first_hour)
    w_draws = np.array([lift_window(ev_counts, base, first_hour, rng.multinomial(len(ev_counts), np.full(len(ev_counts), 1 / len(ev_counts))))
                        for _ in range(B)])
    w_lo, w_hi = np.percentile(w_draws, [2.5, 97.5], axis=0)
    return {
        "events": len(ev_counts),
        "slots_minutes": [k * 15 for k in K],
        "by_slot": {r: {"lift": point[i].round(4).tolist(), "lo": lo[i].round(4).tolist(), "hi": hi[i].round(4).tolist()}
                    for i, r in enumerate(RINGS)},
        "first_hour": {r: {"lift": round(float(w_point[i]), 4), "lo": round(float(w_lo[i]), 4), "hi": round(float(w_hi[i]), 4)}
                       for i, r in enumerate(RINGS)},
        "trips_per_event_first_hour_baseline": {
            r: round(float(base[:, first_hour, i].sum(axis=1).mean()), 1) for i, r in enumerate(RINGS)},
    }


def lift_window(ev_counts, base, window, w=None):
    w = np.ones(len(ev_counts)) if w is None else w
    ev_sum = np.tensordot(w, ev_counts[:, window].sum(axis=1), axes=1)
    base_sum = np.tensordot(w, base[:, window].sum(axis=1), axes=1)
    ratio = ev_sum / base_sum
    return ratio[:3] / ratio[3] - 1


def main():
    con = duckdb.connect(str(DB), read_only=True)
    con.execute(SETUP)
    rng = np.random.default_rng(SEED)
    results = {}

    events, ev_counts, base = per_event(con, "real_ev", "real_ev_st")
    info = {e: (line, t0, d) for e, line, t0, d in con.execute("select e, line, t0, max_delay from real_ev").fetchall()}
    results["all"] = summarise(ev_counts, base, rng)

    groups = {
        "rush hour (7-10am, 4-7pm weekdays)": lambda t0, d: t0.weekday() < 5 and (7 <= t0.hour < 10 or 16 <= t0.hour < 19),
        "off-peak": lambda t0, d: not (t0.weekday() < 5 and (7 <= t0.hour < 10 or 16 <= t0.hour < 19)),
        "delay 10-19 min": lambda t0, d: d < 20,
        "delay 20-59 min": lambda t0, d: 20 <= d < 60,
        "delay 60+ min": lambda t0, d: d >= 60,
    }
    for name, keep in groups.items():
        idx = [i for i, e in enumerate(events) if keep(info[e][1], info[e][2])]
        results[name] = summarise(ev_counts[idx], base[idx], rng)

    # placebo: move each real event 5-9 weeks (same weekday/time) to a moment with no
    # disruption on its line within 3 hours; keep its stations.
    con.execute("""
        create temp table placebo_ev as
        select e, line, t0, max_delay from (
            select r.e, r.line, r.t0 + to_days(7 * s.w) as t0, r.max_delay,
                   row_number() over (partition by r.e order by hash(r.e, s.w)) as pick
            from real_ev r, (select unnest([-9, -8, -7, -6, -5, 5, 6, 7, 8, 9]) as w) s
            where r.t0 + to_days(7 * s.w) between timestamp '2023-02-01' and timestamp '2026-08-31'
              and not exists (select 1 from real_ev x where x.line = r.line
                              and x.t0 between r.t0 + to_days(7 * s.w) - interval 3 hour
                                           and r.t0 + to_days(7 * s.w) + interval 3 hour)
        ) where pick = 1""")
    _, p_ev, p_base = per_event(con, "placebo_ev", "real_ev_st")
    results["placebo (no real disruption)"] = summarise(p_ev, p_base, rng)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=1))

    print(f"{'group':<36} {'events':>6}  first-hour lift by distance (95% range)")
    for name, r in results.items():
        cells = "  ".join(f"{ring}: {v['lift']:+.1%} ({v['lo']:+.1%} to {v['hi']:+.1%})" for ring, v in r["first_hour"].items())
        print(f"{name:<36} {r['events']:>6}  {cells}")
    print("\nbaseline trips per event in the first hour:", results["all"]["trips_per_event_first_hour_baseline"])


if __name__ == "__main__":
    main()
