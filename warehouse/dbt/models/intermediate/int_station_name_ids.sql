-- from warehouse/sql/10_trips.sql
-- trips: one row per Bike Share trip, 2016 onward, in Toronto local time.
-- Input: stg_trips (all text, one format code per source file).

-- 2016 and 2017 Q3-Q4 have station names but no ids: learn name -> id from the years
-- that have both. 2025 end names are copies of start names, so they are not used.
select name, arg_max(station_id, n) as station_id
from (
    select name, station_id, count(*) as n from (
        select clean_name(start_name) as name, clean_id(start_id) as station_id from {{ source('staging', 'stg_trips') }}
        union all
        select clean_name(end_name), clean_id(end_id) from {{ source('staging', 'stg_trips') }} where year <> 2025
    ) where name is not null and station_id is not null
    group by all
)
group by name
