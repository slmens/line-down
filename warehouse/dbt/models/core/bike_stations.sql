-- from warehouse/sql/20_stations.sql
select
    try_cast(s.station_id as integer) as station_id,
    s.name,
    s.lat::double as lat,
    s.lon::double as lon,
    s.capacity::integer as capacity
from (select unnest(data.stations) as s from {{ source('staging', 'bike_station_info') }})
order by station_id
