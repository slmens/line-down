-- from warehouse/sql/20_stations.sql
-- subway_stations: one row per station, platforms grouped, from the TTC GTFS.
-- bike_stations: current Bike Share stations from the newest station_information snapshot.
-- Inputs: gtfs_routes, gtfs_trips, gtfs_stop_times, gtfs_stops, bike_station_info (from build.py).

select distinct s.stop_id, s.stop_name, try_cast(s.stop_lat as double) as lat,
       try_cast(s.stop_lon as double) as lon, r.route_short_name as line
from {{ source('staging', 'gtfs_routes') }} r
join {{ source('staging', 'gtfs_trips') }} t using (route_id)
join {{ source('staging', 'gtfs_stop_times') }} st using (trip_id)
join {{ source('staging', 'gtfs_stops') }} s using (stop_id)
where r.route_type = '1'
