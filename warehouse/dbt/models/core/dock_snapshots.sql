-- from warehouse/sql/40_live.sql
-- Tables from our own live collectors. Times are converted from UTC to Toronto local
-- time so they line up with the history tables.
-- Inputs: live_station_status, live_ttc_alerts (raw snapshot rows, from build.py).

-- Every station_status snapshot we have: gaps here are gaps in collection.
select distinct timezone('America/Toronto', to_timestamp(last_updated)) as observed_at
from {{ source('staging', 'live_station_status') }}
order by 1
