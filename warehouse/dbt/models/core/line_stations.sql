-- from warehouse/sql/20_stations.sql
-- line_stations: each line's stations in running order, from the longest scheduled trip
-- on that line (so short-turn trips do not cut the line short). Lets a delay or alert
-- "between X and Y" be expanded into every station in the stretch.
with trip_len as (
    select r.route_short_name as line, st.trip_id, count(*) as n
    from {{ source('staging', 'gtfs_routes') }} r
    join {{ source('staging', 'gtfs_trips') }} t using (route_id)
    join {{ source('staging', 'gtfs_stop_times') }} st using (trip_id)
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
join {{ source('staging', 'gtfs_stop_times') }} st using (trip_id)
join {{ source('staging', 'gtfs_stops') }} s using (stop_id)
order by l.line, seq
