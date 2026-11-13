-- from warehouse/sql/10_trips.sql
with parsed as (
    select
        try_cast(try_cast(trip_id as double) as bigint) as trip_id,
        parse_trip_time(start_time, time_format) as start_time,
        parse_trip_time(end_time, time_format) as end_time,
        try_cast(try_cast(duration as double) as integer) as duration_s,
        coalesce(clean_id(start_id), s.station_id) as start_station_id,
        coalesce(clean_id(end_id), case when year <> 2025 then e.station_id end) as end_station_id,
        clean_id(start_id) is null and s.station_id is not null as start_id_from_name,
        clean_id(bike_id) as bike_id,
        user_kind(user_type) as user_type,
        nullif(trim(bike_model), '') as bike_model,
        source_file,
        year as file_year
    from {{ source('staging', 'stg_trips') }}
    left join {{ ref('int_station_name_ids') }} s on s.name = clean_name(start_name)
    left join {{ ref('int_station_name_ids') }} e on e.name = clean_name(end_name)
)
-- A trip dated more than a year from its file's year is a bad cell (one 2016 row says 2000).
select * exclude (file_year) from parsed
where start_time is not null and abs(year(start_time) - file_year) <= 1
order by start_time, trip_id, source_file
