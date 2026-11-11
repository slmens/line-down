# History sources: what the raw files look like

Measured 2026-11-10 with stdlib Python (zipfile + csv; XLSX parsed from its sheet XML) against `data/raw/history/`. DuckDB `read_xlsx` was **not** tested yet (venv not created). "Rows" exclude the header.

## TTC subway delays (`ttc-subway-delay-data/`)

Columns everywhere: `Date, Time, Day, Station, Code, Min Delay, Min Gap, Bound, Line, Vehicle` (the 2025+ CSV adds a leading `_id`).

| File | Sheets | Rows | Date / time |
|---|---|---|---|
| jan-2014-april-2017.xlsx | 1 (`Incidents`) | 69,016 | Excel serial (41640) / text `HH:MM` |
| may-december-2017.xlsx | 8, one per month (`May17` … `Dec17`) | 12,929 | same |
| data-2018.xlsx | 12 monthly | 20,737 | same |
| data-2019.xlsx | 12 monthly | 19,222 | same |
| 2020.xlsx | 12 monthly | 14,782 | same |
| 2021.xlsx | 12 monthly | 16,370 | same |
| 2022.xlsx | 1 (`2022`) | 19,895 | same |
| 2023.xlsx | 1 (`2023`) | 22,949 | same |
| 2024.xlsx | 1 (`Subway`) | 26,467 | same |
| data-since-2025.csv | – | 47,915 | `2025-01-01` / `02:10`; UTF-8, no BOM |
| **Total delay rows** | | **270,282** | |

Code lists: `code-descriptions.csv` (140 rows, `_id, CODE, DESCRIPTION`); `ttc-subway-delay-codes.xlsx` (1 sheet `Sheet 1`, header on row 2, two side-by-side tables: SUB codes in C–D, SRT codes in G–H, 130 non-blank rows incl. header); `readme.xlsx` (field descriptions, 10 rows).

Measured: no blank rows, no repeated headers, no empty Station, all Time values `HH:MM`, Min Delay all integers (max 999). Monthly sheet names are inconsistent (`Jan 2020`, `Feb 20`, `March '20`, `June20`).

Station names: 2,235 distinct values; 1,278 are exactly 22 characters (cut off: `PIONEER VILLAGE STATIO`). 128 distinct values contain "BLOOR", e.g. `BLOOR STATION`, `BLOOR SATION`, `BLOOR STATON`, `YONGE BD STATION`, `BLOOR-YONGE STATION`, `YONGE AND BLOOR`, `BLOOR STATION (ENTERIN`, plus line names (`LINE 2 BLOOR-DANFORTH`, ~30 spellings) and segments (`BLOOR TO EGLINTON STAT`). Platform qualifiers: `ST GEORGE BD/YUS STATION`, `KENNEDY BD/SRT STATION`.

Line: `YU` 132,238, `BD` 115,939, `SHP` 9,589, `SRT` 7,673, `YU/BD` 3,373, blank 887, then ~20 spellings (`YUS/BD`, `B/D`, `YU / BD`, `999`, `29 DUFFERIN`…). Bound: blank 74,881; `N/S/E/W`; stray `B`, `Y`, `0`, `5`, `R`.

## Bike Share ridership (`bike-share-toronto-ridership-data/`)

| File | Inner files | Rows | Columns | Start time example | Encoding |
|---|---|---|---|---|---|
| 2014-2015.xlsx | 17 sheets | n/a | **aggregates, not trips**: monthly OD count sheets with a title row above the header (`Start Terminal`…), `Station Key` (81 stations, lat/lon), trips-by-hour, demographics | – | – |
| 2016.xlsx | 2 sheets (`tor_trips_2016_Q3 ` with trailing space, `tor_trips_2016_Q4`) | 585,531 | trip_id, trip_start_time, trip_stop_time, trip_duration_seconds, from/to_station_name, user_type (**no station ids**) | Q3 serial `42560.04`; Q4 mixed, see quirks | – |
| 2017.zip | 4 quarterly CSV + stray `~$…docx` | 1,492,369 | Q1–Q2 as 2016 + from/to_station_id; Q3–Q4 **no ids** | Q1/Q2 `1/4/2017 0:01` (**D/M/Y**), Q3 `7/1/2017 0:00` (M/D/Y), Q4 `10/01/17 00:00:01` | UTF-8 |
| 2018.zip | 4 quarterly | 1,922,955 | trip_id, trip_duration_seconds, from_station_id, trip_start_time, … (reordered) | `1/1/2018 0:47` | UTF-8 |
| 2019.zip | 4 quarterly | 2,439,517 | Trip Id, `Trip  Duration` (2 spaces), Start Station Id, Start Time, Start Station Name, End Station Id, End Time, End Station Name, Bike Id, User Type | `01/01/2019 00:08` | UTF-8 BOM |
| 2020.zip | 12 monthly | 2,911,308 | as 2019 | `01/01/2020 00:08` | UTF-8 BOM |
| 2021.zip | 12 monthly | 3,575,182 | as 2019 | `01/01/2021 00:04` | BOM, but 01 and 05 are cp1252 |
| 2022.zip | 11 CSV + `2022-11.zip` nested zip (320,229 rows, no BOM) | 4,620,469 | as 2019 | `01/01/2022 00:02` | UTF-8 BOM |
| 2023.zip | 12 monthly | 5,713,141 | as 2019 | `01/01/2023 00:00` | 04–11 cp1252, rest BOM |
| 2024.zip | 1 CSV | 6,953,094 | Trip_Id, Trip_Duration, Start_Station_Id, Start_Time, Start_Station_Name, End_Station_Id, End_Time, End_Station_Name, Bike_Id, User_Type, Bike_Model | `2024-01-01 00:00:08` | UTF-8 |
| 2025.zip | 12 monthly (`bikeshare_2025_MM.csv`) | 7,812,520 | as 2024 | `2025-01-01 00:02:15` | 01–10 cp1252, 11–12 UTF-8 |
| 2026.zip | 1 CSV, ends 2026-09-30 23:59 | 6,830,174 | as 2024 | `2026-01-01 00:00:26` | UTF-8 |
| **Total trip rows (2016–2026)** | | **44,856,260** | | | |

Readme: `bikeshare-ridership-readme.xlsx`, 2 sheets of field definitions.

## TTC GTFS (`ttc-routes-and-schedules/…/opendata_ttc_schedules.zip`)

Files: agency, calendar, calendar_dates, routes, shapes, stops, stop_times, trips. Subway = `route_type` 1: routes 1 (Yonge-University), 2 (Bloor - Danforth), 4 (Sheppard). Line 3 SRT is absent. Through trips → stop_times there are 148 subway stop_ids, each a **platform** (`Bloor Station - Northbound Platform`, `Yonge Station - Westbound Platform`). `parent_station` and `location_type` columns exist but are empty everywhere (0 stations with location_type 1). Stations must be grouped by stripping ` - … Platform` from stop_name. Bloor-Yonge appears as two names, `Bloor Station` and `Yonge Station`, one per line.

## Quirks the load must handle

1. **Bike dates change format by file**: Excel serials (2016 Q3); 2016 Q4 mixes text `13/10/2016 0:00` (D/M/Y, 115,711 rows) with serials (101,858) that Excel parsed month/day swapped (the range spans Jan–Dec for a Q4 file); 2017 Q1–Q2 D/M/Y; 2017 Q3–2023 M/D/Y (2017 Q4 uses 2-digit years); 2024+ ISO. One 2016 Q3 serial is 2000-01-01.
2. **Station ids missing** in 2016 and 2017 Q3–Q4 (names only). From 2022, names can be literal `NULL` while the id is present. 2024 and 2026 End_Station_Id is a float string (`7130.0`), and 8,424 / 6,761 / 12,951 end ids are blank in 2024/25/26; 7 start ids are blank in 2025. 2025 End_Station_Name is wrong: it equals Start_Station_Name on 6.8M of 7.8M rows whose ids differ. Use ids, not names.
3. **Delay station names are free text**: truncated to 22 chars, misspelt, platform-qualified (`BD`/`YUS`), or not a station at all (line names, `X TO Y` segments). 2,235 distinct values must map onto about 75 stations. Line also has ~25 spellings plus non-subway values.
4. **Encoding and structure vary**: UTF-8 BOM, plain UTF-8 and cp1252 files mixed in one zip; a nested zip (2022-11); a stray Office lock file (2017); 4 header layouts (snake_case, `Trip  Duration` with double space, `Trip_Id` style, column order changed in 2018); multi-sheet XLSX with irregular sheet names and a trailing space.
5. **Bad bike rows**: 2020-10 has 249 rows with 9 instead of 10 fields; trip id and duration look fused (`10000084625`). 2019 has 16 blank durations. Durations <60 s are common (e.g. 17,782 in 2024) and >24 h appear (max 12.4M s ≈ 143 days); 2025 looks capped near 1 day. 2014–2015 data is aggregate counts only, not trips.

Not measured: duplicate trip_ids across files, end-time vs duration consistency, delay `Day` vs `Date` agreement, GTFS station coordinates vs bike stations.

- `read_xlsx` reads only the first sheet unless `sheet=` is given. Delay workbooks have one sheet per month with hand-typed names (2020: `Jan 2020`, `Feb 20`, `March '20`, `June20`…) and bike 2016 has two quarterly sheets (`tor_trips_2016_Q3 ` with a trailing space). The load must list sheets from `xl/workbook.xml` and read each one. Checked with DuckDB 2.0.0 on 2026-11-10.
