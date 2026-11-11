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
- Collectors and download pipeline stay on `/usr/bin/python3` 3.9, stdlib only.
- Warehouse: DuckDB pinned in `requirements.txt` (2.0.0 needs Python >= 3.11), in `.venv/` on Python 3.12 via uv at `~/.local/bin/uv`. Created 2026-11-10 (Python 3.12.16). DuckDB's `excel` extension is fetched once from the official DuckDB repository (signature-checked) into `~/.duckdb/extensions/`.
- Runs on a Mac mini under launchd.

## Commands

- Test: `.venv/bin/python -m unittest` (all); `python3 -m unittest` runs collector tests only, warehouse tests skip without DuckDB
- Disruption finding: `.venv/bin/python analysis/disruption_effect.py && .venv/bin/python analysis/plot_effect.py` (writes `analysis/output/`; write-up in `analysis/FINDING.md`)
- Delay-length model: `.venv/bin/python models/delay_length.py` (write-up in `models/DELAY_LENGTH.md`)
- Walk-or-wait advisor: `.venv/bin/python models/walk_or_wait.py` (scores it); add `"<station>" "<next station>" <code> <minutes>` for advice (write-up in `models/WALK_OR_WAIT.md`)
- Pixel map: `.venv/bin/python map/export.py` (about 25 s, writes `map/data.js`), then open `map/index.html` in a browser (works from disk; or `python3 -m http.server 8765 -d map`)
- Build the warehouse: `.venv/bin/python warehouse/build.py` (about 70 s, uses all cores; `--twice` also checks the rebuild is identical). Output `data/warehouse/linedown.duckdb`
- One bike share snapshot: `python3 collectors/bikeshare.py station_status`
- One TTC alerts snapshot: `python3 collectors/ttc.py`
- Check for stopped collectors: `python3 collectors/check_fresh.py` (also pings the URL in `data/heartbeat_url`, if present, when all feeds are fresh)
- Download or refresh history: `python3 pipelines/download_history.py` (re-runnable; skips what it has; launchd runs it weekly)
- Create warehouse venv: `~/.local/bin/uv python install 3.12 && { [ -d .venv ] || ~/.local/bin/uv venv --python 3.12 .venv; } && ~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt`
- Run warehouse code: `.venv/bin/python <script>`
- Start collectors on this Mac: `sh collectors/install_launchd.sh` (logs in `data/logs/`)

## Decisions

Add one line per decision that code alone would not explain, with the date.

- 2026-11-10: Live bike share collector built first: dock levels have no public history, so every day not collected is lost.
- 2026-11-10: Raw snapshots stored gzipped as `data/raw/bikeshare/<feed>/<UTC date>/<last_updated>.json.gz`; UTC so DST never splits or merges hours.
- 2026-11-10: Collector is one fetch per run, scheduled by launchd (status 30s, station info hourly); the next run is the retry.
- 2026-11-10: TTC alerts from `alerts.ttc.ca/api/alerts/live-alerts`, stored only when the body's SHA-256 changes. Its `lastUpdated` is Toronto local time mislabelled `Z`; files are named by our fetch time instead.
- 2026-11-10: All downloads go through `collectors/common.py`: HTTPS only, certificates verified, no redirects to another host, 10 MB cap, shape checked before saving. Downloads are never executed.
- 2026-11-10: Each feed folder has a `LAST` file touched on every successful run; `check_fresh.py` (every 5 min) sends a macOS notification when one is too old.
- 2026-11-10: History comes from Toronto Open Data (CKAN) datasets `ttc-subway-delay-data`, `bike-share-toronto-ridership-data` and `ttc-routes-and-schedules` (GTFS, for subway station locations), saved untouched under `data/raw/history/<dataset>/<last-modified date>/`. Only CSV/XLSX/ZIP are kept (XML/JSON are copies). Each file is checked against the server Content-Length (the portal listing sizes are stale for some files) and zip CRCs verified; nothing is unzipped on disk.
- 2026-11-10: Warehouse = one DuckDB file rebuilt from scratch by `warehouse/build.py`: zips unpacked to a scratch dir as UTF-8, all-text staging, then `warehouse/sql/*.sql` in order. File quirks are in `warehouse/SOURCES.md`.
- 2026-11-10: All warehouse times are Toronto local time (history is published that way; live UTC is converted).
- 2026-11-10: Delay station text is matched to GTFS stations by key cleaning + `warehouse/seeds/station_aliases.csv` + unique prefix (among the delay's own line's stations when the line is known); line names and Scarborough RT stations stay unmatched (~9% of rows, 1.5% of 10+ min delays on Lines 1/2/4). Bloor and Yonge are merged into Bloor-Yonge.
- 2026-11-10: A delay "X TO Y" means the whole stretch was affected: `subway_delays.station`/`station_to` hold the ends (both must be on the delay's line) and `delay_stations` lists every station between them, using `line_stations` order from GTFS.
- 2026-11-10: Trips before 2023 are not important to the analysis; their 10-14% of trips at since-closed stations (no location) is accepted.
- 2026-11-10: 2016 and 2017 Q3-Q4 trips have no station ids; ids are filled from names learned in other years (2025 end names excluded: they copy the start name).
- 2026-11-11: Finding method: difference-in-differences event study (10+ min delays 2023-02 to 2026-08, rings 0-250/250-500/500-1000 m, matched same-weekday control days ±1-4 weeks, >2 km stations as citywide control, event bootstrap, fake-event placebo). Analysis needs numpy and matplotlib (pinned in requirements.txt).
- 2026-11-11: Delay-length model scored once on held-out 2025-2026: MAE 3.88 vs 4.01 for the per-cause-code median baseline; no gain for 20+ min warnings. 2025-2026 is now spent as a test set; tune any new model on other years. scikit-learn pinned.
- 2026-11-11: Walk-or-wait rule uses real median Bike Share ride times between the docks (54 of 142 routes have 20+ trips; others 15 km/h). Built on 2014-2021, scored on 2022 (beats always wait/bike/walk at 5/10/15 min). Test years spent so far: 2022, 2023-2024, 2025-2026. Assumes bikes are available until live dock history exists.
- 2026-11-11: Pixel map v1 replays history only (no live layer yet): the 8 longest non-weather delays since 2023 (one per day, 10+ bike stations and 20+ normal trips within 1 km), replayed as two maps on one clock: every real trip starting within 2.5 km, drawn as a straight line dock to dock, on the day and on one normal day (same weekday and time ±1-4 weeks, no delay on the line) picked by a fixed rule: trip count closest to the average of all normal days. Headline and counters count trips started within 1 km in the hour after the delay. No citywide control per event, so the page says one day can be partly chance and quotes the averaged finding. Drawn only from our own data, no map tiles: subway lines from GTFS shapes, Lake Ontario's shore traced as the smoothed southern edge of all bus/streetcar shapes; turned 17° so Yonge runs straight up. Pixel art at 2 device pixels per art pixel, each colour snapped on/off (no blur).

## Agent config

- `.claude/rules/` — rules scoped to one area (e.g. SQL style, collector conventions)
- `.claude/skills/` — repeatable workflows (e.g. backfill a feed, score a model)
- `.claude/agents/` — subagents for specialised jobs

Keep this file short. When a section grows past a screen, move it into `.claude/rules/` and link it.
