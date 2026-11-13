# Tableau Public dashboards

*Data: `.venv/bin/python bi/export_extracts.py` writes `data/exports/*.csv` (Dagster's `tableau_extracts` asset does it daily). Tableau Public can't open DuckDB, so it reads these files.*

Tableau Public saves only to the web, so the workbook lives on the public profile, not in this repo. To refresh: open it in Tableau Public, **Data → Refresh All Extracts**, then **File → Save to Tableau Public**. Everything here is open city data plus our own dock snapshots, so public is fine.

Published: *(add the URL here once it's up)*

## Honesty rules (from CLAUDE.md principles)

- Show the uncertainty. Every lift gets its 95% range (`lo`–`hi`) as error bars or a band, never the headline number alone.
- Say how much data a number rests on (`events`, incident count).
- Lifts are fractions. Format as percent (0.136 → +13.6%).

## 1. Disruption finding

| File | Rows |
|---|---|
| `finding_first_hour.csv` | group × ring: `events`, `lift`, `lo`, `hi`, `baseline_trips_per_event` |
| `finding_over_time.csv` | group × ring × `minutes_from_delay` (−60 to +165): `lift`, `lo`, `hi` |

- **Headline bars:** filter `group = all`; `ring` on columns, `lift` as bars, `lo`/`hi` as error bars (reference band or a Gantt bar from `lo` sized `hi − lo`). Title: Bike Share trips near a 10+ minute subway delay, first hour.
- **Over time:** filter `group = all`; `minutes_from_delay` on columns, `lift` as a line with a `lo`–`hi` band, one colour per `ring`; reference line at 0 minutes ("delay starts").
- **By group:** first-hour lift per `group` (rush hour, off-peak, delay length) as small multiples. Include the `placebo (no real disruption)` group: it should sit near zero, and showing it is what makes the rest believable.
- Caption: the method in one line (difference-in-differences, matched normal days, >2 km stations as citywide control) and a link to `analysis/FINDING.md`.

## 2. Delay explorer

`delays_monthly.csv`: `month`, `line`, `station` (blank = text not matched to a station), `code`, `cause`, `delays`, `delays_10_plus_min`, `total_delay_min`, `median_delay_min`.

- Filters: line, cause, date range.
- Sheets: delays per month by line (line chart); top stations by `delays_10_plus_min` (bar); top causes (bar).
- `median_delay_min` is a median within each row; don't average it across rows. Use `total_delay_min / delays` for a mean.
- Note blank stations as "not matched (~9% of rows)".

## 3. Agent scorecard

`agent_incidents.csv`: one row per incident; `estimate_median_min`, `estimate_8_in_10_under_min`, `actual_min`, `baseline_median_min`, the two `abs_error_min` columns, `within_bound`, `faithful`.

- KPI tiles: incidents, faithful share, share `within_bound` (target about 80%), mean `abs_error_min` vs mean `baseline_abs_error_min`.
- Scatter: `estimate_median_min` vs `actual_min`, with a y = x line.
- Always show the incident count and "too few incidents to judge" while it is under a few hundred. The estimate is from delay-log lengths, the outcome is how long the alert stayed up (see `agent/AGENT.md`).

## 4. Live docks

`dock_levels_hourly.csv`: per subway station, at the top of each hour since collection began (2026-11-10): `docks_reporting`, `bikes`, `free_docks`, `docks_with_2_or_fewer_bikes`, all within 500 m.

- Station picker; `bikes` over `at_hour` as a line.
- Heatmap: station × hour of day, average `bikes`.
- Note that it covers only days the collector ran, and grows daily.
