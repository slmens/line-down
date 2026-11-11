-- subway_delays: one row per recorded subway delay, 2014 onward, Toronto local time,
-- with the raw station text matched to subway_stations where possible.
-- delay_codes: code -> description. Inputs: stg_delays, stg_delay_codes, seed_station_aliases.

create table delay_codes as
select distinct upper(trim("CODE")) as code, trim("DESCRIPTION") as description
from stg_delay_codes
where nullif(trim("CODE"), '') is not null
order by code;

create temp table station_keys as
select station, station_key(station) as key from subway_stations;

-- Each distinct raw name is matched once: alias seed, then exact key, then unique prefix
-- (names are cut at 22 characters). "X TO Y" segments and line names stay unmatched.
create temp table raw_station_match as
with raw as (
    select distinct station as raw, station_key(station) as key from stg_delays
),
prefix as (
    select r.raw, any_value(k.station) as station
    from raw r join station_keys k on starts_with(k.key, r.key) and length(r.key) >= 4
    group by r.raw
    having count(distinct k.station) = 1
)
select r.raw, coalesce(a.station, x.station, p.station) as station
from raw r
left join seed_station_aliases a on a.key = r.key
left join station_keys x on x.key = r.key
left join prefix p on p.raw = r.raw
where r.raw not like '% TO %';

create table subway_delays as
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
    from stg_delays
)
select
    row_number() over (order by day_date, time_of_day, station_raw, code, min_delay, min_gap,
                       bound, line_raw, vehicle, source_file) as delay_id,
    day_date + time_of_day as occurred_at,
    m.station,
    p.* exclude (day_date, time_of_day, station)
from parsed p
left join raw_station_match m on m.raw = p.station
where day_date is not null and time_of_day is not null
order by delay_id;
