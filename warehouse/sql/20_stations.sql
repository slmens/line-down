-- subway_stations: one row per station, platforms grouped, from the TTC GTFS.
-- bike_stations: current Bike Share stations from the newest station_information snapshot.
-- Inputs: gtfs_routes, gtfs_trips, gtfs_stop_times, gtfs_stops, bike_station_info (from build.py).

create table subway_platforms as
select distinct s.stop_id, s.stop_name, try_cast(s.stop_lat as double) as lat,
       try_cast(s.stop_lon as double) as lon, r.route_short_name as line
from gtfs_routes r
join gtfs_trips t using (route_id)
join gtfs_stop_times st using (trip_id)
join gtfs_stops s using (stop_id)
where r.route_type = '1';

create table subway_stations as
select
    -- Bloor (Line 1) and Yonge (Line 2) are one interchange.
    case when base in ('Bloor Station', 'Yonge Station') then 'Bloor-Yonge Station' else base end as station,
    -- rounded so parallel summation order cannot change the result between builds (6 dp ~ 10 cm)
    round(avg(lat), 6) as lat,
    round(avg(lon), 6) as lon,
    string_agg(distinct line, ',' order by line) as lines,
    count(*) as platforms
from (select *, regexp_replace(stop_name, ' - .*$', '') as base from subway_platforms)
group by 1
order by 1;

-- line_stations: each line's stations in running order, from the longest scheduled trip
-- on that line (so short-turn trips do not cut the line short). Lets a delay or alert
-- "between X and Y" be expanded into every station in the stretch.
create table line_stations as
with trip_len as (
    select r.route_short_name as line, st.trip_id, count(*) as n
    from gtfs_routes r
    join gtfs_trips t using (route_id)
    join gtfs_stop_times st using (trip_id)
    where r.route_type = '1'
    group by all
),
longest as (
    select line, trip_id from (
        select *, row_number() over (partition by line order by n desc, trip_id) as rn from trip_len
    ) where rn = 1
)
select
    l.line,
    row_number() over (partition by l.line order by try_cast(st.stop_sequence as integer)) as seq,
    case when regexp_replace(s.stop_name, ' - .*$', '') in ('Bloor Station', 'Yonge Station')
         then 'Bloor-Yonge Station' else regexp_replace(s.stop_name, ' - .*$', '') end as station
from longest l
join gtfs_stop_times st using (trip_id)
join gtfs_stops s using (stop_id)
order by l.line, seq;

create table bike_stations as
select
    try_cast(s.station_id as integer) as station_id,
    s.name,
    s.lat::double as lat,
    s.lon::double as lon,
    s.capacity::integer as capacity
from (select unnest(data.stations) as s from bike_station_info)
order by station_id;
