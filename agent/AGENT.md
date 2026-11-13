# Incident briefs

*Run: launchd runs `.venv/bin/python agent/brief.py` every minute. Score: `.venv/bin/python agent/brief.py score` (writes `agent/output/scores.json`).*

## What it does

1. **Spots a disruption.** It reads every new TTC alert snapshot. A subway alert counts if it is not planned maintenance and says no service, delays or reduced service. It ends at the first snapshot where the alert is gone or says "Regular service".
2. **Gathers facts from our own data**, frozen at the moment the alert appeared:
   - the affected stations (alert ends matched to GTFS station order),
   - how long past delays with that cause lasted (TTC delay log, 5+ minute delays; alert cause text mapped to delay codes in `CAUSE_CODES`),
   - the Bike Share effect by distance in the first hour (`analysis/output/results.json`),
   - bikes at docks within 500 m, from the station_status snapshot taken just before the alert.
3. **Claude writes 3-5 sentences** from those facts only (`anthropic/claude-haiku-5.5` through OpenRouter, low effort, one call per incident).
4. **Scores itself** once the alert clears.

Incidents are saved in `data/agent/incidents/<alert id>.json` (alert, facts, brief, outcome).

## How it is scored

| Check | Compared with |
|---|---|
| Length: actual alert duration vs the usual-length median for that cause | Baseline: the median across all causes |
| Calibration: share of incidents shorter than the "8 in 10 under" bound | Should be about 80% |
| Faithfulness: every number in the brief appears in the facts | Should be 100% |

## Latest result (18 incidents, 2026-11-10 to 11-12, all briefed)

All 18 briefs are faithful: every number appears in the facts. All were briefed on 2026-11-12 when the API key was added, from facts frozen at each alert's start.

Per-cause median error 12.8 min vs 12.7 min for the all-causes baseline, so the per-cause estimate does no better yet. 72% of incidents finished within the 8-in-10 bound (should be about 80%). Alerts lasted 0.5 to 114 minutes (median 6.5). That's too few incidents to conclude anything, and the one 114-minute delay dominates the error. A known mismatch: the estimate comes from delay-log lengths, while the outcome is how long the alert stayed up. The two may differ in a consistent way, and that can be measured once there are a few weeks of incidents.
