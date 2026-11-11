# Stuck in a subway delay: wait, walk or take a bike?

*Reproduce: `.venv/bin/python models/walk_or_wait.py` (a few seconds, after `warehouse/build.py`). Advice for one case: `.venv/bin/python models/walk_or_wait.py "St Andrew Station" "Union Station" SUUT 10`. Numbers from `models/output/walk_or_wait_metrics.json`, 2026-11-11.*

## The question

You're on a subway platform. A delay has been going on for 10 minutes. You want to get to the next station. Should you wait, walk, or take a Bike Share bike?

Example answer:

```
About even: the bike beats waiting in 43% of past cases.
  Wait: about 8 min to reach Union Station (8 in 10 times under 18), based on 1,500 past 'SUUT' delays that lasted 10+ min.
  Bike: 10 min. Dock 14 m away, real median ride 4.3 min over 68 trips, dock 19 m from Union Station. Assumes a bike is there.
  Walk: 12 min (0.5 km).
```

## Where each number comes from: measured or assumed

| Part | Source | Measured? |
|---|---|---|
| How much longer the delay lasts | TTC delay log: past delays with the same cause that had already lasted this long | **Yes**, real delays |
| Train ride to the next station once it moves | flat 2 minutes | No, assumed |
| Platform to street, unlock bike | 3 minutes | No, assumed |
| Street to platform at the other end | 2 minutes | No, assumed |
| Walk from station to dock, dock to station | distance x1.3 at 4.8 km/h | Distance yes, speed assumed |
| **Bike ride between the two docks** | **median of real Bike Share trips between those exact docks**, when there are 20+ of them | **Yes on 54 of 142 routes**; the rest use 15 km/h |
| Walking the whole way | distance x1.3 at 4.8 km/h | Distance yes, speed assumed |
| A bike is at the dock | assumed | No (live dock data will fix this) |

**Nobody was observed walking or biking out of a delay.** The test below asks: if a person had followed this advice during a real past delay, would they have arrived sooner? The waiting time uses what the delay really did; the bike time uses what real riders took on that route that year.

## How it was tested

Four imaginary riders face every real delay in **2022**:
- **Waiter:** always stays on the platform.
- **Cyclist:** always leaves and takes a bike.
- **Walker:** always leaves and walks.
- **Our rule:** leaves only if, in past delays like this one, waiting was slower more than half the time.

The rule was built only from **2014-2021** delays and bike trips, so 2022 is new to it. (2023-2024 were used to test an earlier version and 2025-2026 for another model, so they are not used here.)

## Results on 2022

Average minutes to reach the next station:

| Delay already lasted | Our rule | Waiter | Cyclist | Walker | Perfect hindsight |
|---|---|---|---|---|---|
| 5 min (8,110 cases) | **7.8** | 8.7 | 17.6 | 22.3 | 6.0 |
| 10 min (2,797) | **11.5** | 14.0 | 16.6 | 21.5 | 7.7 |
| 15 min (1,421) | **14.8** | 19.2 | 16.3 | 21.6 | 8.7 |

- After 10 minutes, the rule gets you there **2.5 minutes sooner than always waiting** (95% range 1.8 to 3.2).
- After 15 minutes, **4.4 minutes sooner than always waiting** (3.2 to 5.6) and **1.6 minutes sooner than always biking** (0.2 to 3.0).
- "Perfect hindsight" is a rider who magically knew how long the delay would last. No rule can reach it; it shows how much room is left.

## What it says

- **Usually, wait.** The rule says wait in over 90% of cases. Most delays end within a few more minutes, and leaving costs about 5 minutes before you even start moving.
- **The bike only wins when the delay runs long and the docks are right at the station exits**, mostly downtown.
- **Walking almost never wins.**

## Limits

- **The 5 minutes for leaving and re-entering the station is a guess**, and on short routes it is most of the bike's total. If it's really 3 minutes, the bike wins more often.
- **Real ride times cover 54 of 142 routes.** The rest still use an estimated speed.
- **Assumes a bike and a free dock are there.**
- **The delay log records how late trains were**, not exactly when service resumed for someone on the platform.
- **The target is the next station**, not your real destination. A closure covering several stations isn't handled yet.
- **Live alerts have no cause code**, only text, so a live version needs the text matched to codes.
