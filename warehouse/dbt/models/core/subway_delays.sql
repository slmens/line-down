-- from warehouse/sql/30_delays.sql
with parsed as (
    select
        coalesce(try_strptime(date, '%Y-%m-%d')::date,
                 date '1899-12-30' + try_cast(try_cast(date as double) as integer)) as day_date,
        try_strptime(time, '%H:%M')::time as time_of_day,
        trim(station) as station_raw,
        upper(nullif(trim(code), '')) as code,
        try_cast(try_cast(min_delay as double) as integer) as min_delay,
        try_cast(try_cast(min_gap as double) as integer) as min_gap,
        case when upper(trim(bound)) in ('N', 'S', 'E', 'W') then upper(trim(bound)) end as bound,
        line as line_raw,
        subway_line(line) as line,
        clean_id(vehicle) as vehicle,
        source_file,
        station
    from {{ source('staging', 'stg_delays') }}
)
select
    row_number() over (order by day_date, time_of_day, station_raw, code, min_delay, min_gap,
                       bound, line_raw, vehicle, source_file) as delay_id,
    day_date + time_of_day as occurred_at,
    m.station,
    m.station_to,
    p.* exclude (day_date, time_of_day, station)
from parsed p
left join {{ ref('int_raw_station_match') }} m on m.raw = p.station and m.line is not distinct from p.line
where day_date is not null and time_of_day is not null
order by delay_id
