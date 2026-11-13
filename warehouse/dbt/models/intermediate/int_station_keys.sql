-- from warehouse/sql/30_delays.sql
select station, station_key(station) as key from {{ ref('subway_stations') }}
