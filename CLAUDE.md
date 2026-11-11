# Line Down

Watches Toronto's transport network and measures what happens when part of it fails. Core case: a subway disruption and how it spreads to nearby bike share stations. Full brief: [line-down-summary.md](line-down-summary.md).

## Layout

| Folder | Holds |
|--------|-------|
| `collectors/` | Live feeds: TTC alerts, bike share |
| `pipelines/` | Historical loads and transforms |
| `warehouse/` | Schemas and SQL |
| `analysis/` | The disruption finding |
| `models/` | Delay and dock predictions |
| `agent/` | Incident briefs |
| `map/` | The pixel map of Toronto |
| `tests/` | Tests |
| `data/` | Local raw files, never committed |

## Principles

- Pipelines are tested and re-runnable.
- Statistics are honest: report uncertainty, not just the headline.
- Every model is scored against a simple baseline.
- The agent's accuracy is measured and published.

## Stack

- Python 3.9 (macOS system `/usr/bin/python3`), standard library only so far.
- Tests: `unittest` (stdlib).
- Warehouse: DuckDB (planned, not set up yet).
- Runs on a Mac mini under launchd.

## Commands

- Test: `python3 -m unittest`
- One bike share snapshot: `python3 collectors/bikeshare.py station_status`
- Start collectors on this Mac: `sh collectors/install_launchd.sh` (logs in `data/logs/`)

## Decisions

Add one line per decision that code alone would not explain, with the date.

- 2026-11-10: Live bike share collector built first: dock levels have no public history, so every day not collected is lost.
- 2026-11-10: Raw snapshots stored gzipped as `data/raw/bikeshare/<feed>/<UTC date>/<last_updated>.json.gz`; UTC so DST never splits or merges hours.
- 2026-11-10: Collector is one fetch per run, scheduled by launchd (status 30s, station info hourly); the next run is the retry.

## Agent config

- `.claude/rules/` — rules scoped to one area (e.g. SQL style, collector conventions)
- `.claude/skills/` — repeatable workflows (e.g. backfill a feed, score a model)
- `.claude/agents/` — subagents for specialised jobs

Keep this file short. When a section grows past a screen, move it into `.claude/rules/` and link it.
