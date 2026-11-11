# Stuck in a subway delay: wait, walk or take a bike?

*Reproduce: `.venv/bin/python models/walk_or_wait.py` (1 second, after `warehouse/build.py`). Advice for one case: `.venv/bin/python models/walk_or_wait.py "St Andrew Station" "Union Station" SUUT 10`. Numbers from `models/output/walk_or_wait_metrics.json`, 2026-11-11.*

## The question

You're at a subway station, a delay has been going on for 10 minutes, and you want to reach the next station. Wait, walk, or take a Bike Share bike?

Example output:

```
About even: the bike beats waiting in 52% of past cases.
  Wait: about 8 min to reach Union Station (8 in 10 times under 18), based on 1,500 past 'SUUT' delays that lasted 10+ min.
  Bike: 8 min. Nearest dock 14 m away, ride 0.6 km, dock 19 m from Union Station. Assumes a bike is there.
  Walk: 12 min (0.5 km).
```

## How it decides

- **Wait** = how much longer past delays with the same cause ran *after already lasting this long*, plus a 2-minute train ride.
- **Bike** = 3 min to get out and unlock, walk to the nearest dock, ride to the dock nearest the next station, walk in, 2 min to the platform.
- **Walk** = 3 min out, walk, 2 min in.
- Walking 4.8 km/h, cycling 15 km/h, streets 1.3x the straight line.
- **Leave if waiting was slower in more than half of past cases**; otherwise wait.

## Results: 2023-2024, not used to build the rule (built on 2014-2022)

Average minutes to reach the next station, one rider each way per delay at a single station:

| Delay already lasted | Rule | Always wait | Always bike | Always walk | Best possible (hindsight) |
|---|---|---|---|---|---|
| 5 min (18,323 riders) | **7.5** | 8.1 | 16.2 | 21.6 | 5.9 |
| 10 min (6,219) | **10.9** | 12.5 | 15.7 | 21.5 | 7.6 |
| 15 min (3,154) | **13.1** | 16.2 | 15.8 | 21.7 | 8.4 |

- At 10 minutes the rule saves **1.6 min vs always waiting** (95% range 1.3 to 1.9).
- At 15 minutes it saves **3.2 min vs always waiting** (2.6 to 3.8) and **2.7 min vs always biking** (1.7 to 3.5).
- It beats every simple strategy at every point checked.

## What it says about Toronto

- **Waiting is usually right.** The rule waits in about 95% of cases: most delays, even after 10 minutes, end within a few more minutes, and stations are about 1 km apart, so biking takes about 15 minutes door to door.
- **The bike wins where stations are close and docks sit at the exits** (downtown: St Andrew to Union is 8 minutes), and for causes that run long (person at track level, police matters).
- **Walking almost never wins**, except between stations a few hundred metres apart.
- **It gets more useful the longer you've waited.** The gain over "always wait" grows from 0.6 min at 5 minutes to 3.2 min at 15.

## Limits

- **Assumes a bike and a free dock are there.** Live dock data (collected since 2026-11-10) can replace this assumption once there is enough of it.
- **The delay log records how late trains were**, not exactly when service resumed for someone on the platform.
- **The target is the next station.** It doesn't know your real destination, and assumes trains run from there. For a stretch closure the right target is past the stretch; not handled yet.
- **Live alerts have no cause code**, only text; a live version needs the text mapped to codes.
- **Fixed speeds and a flat 2 minutes per stop**: no traffic, hills, weather or real run times.
- **The 50% rule targets "more likely faster", not the lowest average time.** A rule based on the average might do better, but must be tested on years other than 2023-2024, which are now used.
