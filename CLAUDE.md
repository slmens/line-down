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
- One TTC alerts snapshot: `python3 collectors/ttc.py`
- Check for stopped collectors: `python3 collectors/check_fresh.py`
- Download or refresh history: `python3 pipelines/download_history.py` (re-runnable; skips what it has)
- Start collectors on this Mac: `sh collectors/install_launchd.sh` (logs in `data/logs/`)

## Decisions

Add one line per decision that code alone would not explain, with the date.

- 2026-11-10: Live bike share collector built first: dock levels have no public history, so every day not collected is lost.
- 2026-11-10: Raw snapshots stored gzipped as `data/raw/bikeshare/<feed>/<UTC date>/<last_updated>.json.gz`; UTC so DST never splits or merges hours.
- 2026-11-10: Collector is one fetch per run, scheduled by launchd (status 30s, station info hourly); the next run is the retry.
- 2026-11-10: TTC alerts from `alerts.ttc.ca/api/alerts/live-alerts`, stored only when the body's SHA-256 changes. Its `lastUpdated` is Toronto local time mislabelled `Z`; files are named by our fetch time instead.
- 2026-11-10: All downloads go through `collectors/common.py`: HTTPS only, certificates verified, no redirects to another host, 10 MB cap, shape checked before saving. Downloads are never executed.
- 2026-11-10: Each feed folder has a `LAST` file touched on every successful run; `check_fresh.py` (every 5 min) sends a macOS notification when one is too old.
- 2026-11-10: History comes from Toronto Open Data (CKAN) datasets `ttc-subway-delay-data` and `bike-share-toronto-ridership-data`, saved untouched under `data/raw/history/<dataset>/<last-modified date>/`. Only CSV/XLSX/ZIP are kept (XML/JSON are copies). Each file is checked against the server Content-Length (the portal listing sizes are stale for some files) and zip CRCs verified; nothing is unzipped on disk.

## Agent config

- `.claude/rules/` — rules scoped to one area (e.g. SQL style, collector conventions)
- `.claude/skills/` — repeatable workflows (e.g. backfill a feed, score a model)
- `.claude/agents/` — subagents for specialised jobs

Keep this file short. When a section grows past a screen, move it into `.claude/rules/` and link it.
