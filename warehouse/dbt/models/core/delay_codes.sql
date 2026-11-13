-- from warehouse/sql/30_delays.sql
-- subway_delays: one row per recorded subway delay, 2014 onward, Toronto local time,
-- with the raw station text matched to subway_stations where possible.
-- delay_stations: every station each delay affected (a stretch "X TO Y" expands to all
-- stations between X and Y on that line).
-- delay_codes: code -> description.
-- Inputs: stg_delays, stg_delay_codes, seed_station_aliases, subway_stations, line_stations.

-- The city's file is UTF-8 encoded twice: an en dash arrives as the three characters
-- U+00E2 U+0080 U+0093. These are the only such sequences in it (checked 2026-11-11).
select distinct upper(trim("CODE")) as code,
    replace(replace(replace(trim("DESCRIPTION"),
        chr(226) || chr(128) || chr(147), '–'),
        chr(226) || chr(128) || chr(156), '“'),
        chr(226) || chr(128) || chr(157), '”') as description
from {{ source('staging', 'stg_delay_codes') }}
where nullif(trim("CODE"), '') is not null
order by code
