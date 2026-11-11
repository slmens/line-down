-- subway_delays: one row per recorded subway delay, 2014 onward, Toronto local time,
-- with the raw station text matched to subway_stations where possible.
-- delay_stations: every station each delay affected (a stretch "X TO Y" expands to all
-- stations between X and Y on that line).
-- delay_codes: code -> description.
-- Inputs: stg_delays, stg_delay_codes, seed_station_aliases, subway_stations, line_stations.

create table delay_codes as
-- The city's file is UTF-8 encoded twice: an en dash arrives as the three characters
-- U+00E2 U+0080 U+0093. These are the only such sequences in it (checked 2026-11-11).
select distinct upper(trim("CODE")) as code,
    replace(replace(replace(trim("DESCRIPTION"),
        chr(226) || chr(128) || chr(147), '–'),
        chr(226) || chr(128) || chr(156), '“'),
        chr(226) || chr(128) || chr(157), '”') as description
from stg_delay_codes
where nullif(trim("CODE"), '') is not null
order by code;

create temp table station_keys as
select station, station_key(station) as key from subway_stations;

-- Each distinct (raw text, line). "X TO Y" is a stretch: split into its two ends.
create temp table raw_texts as
select distinct
    station as raw,
    subway_line(line) as line,
    station like '% TO %' as is_stretch,
    case when station like '% TO %' then split_part(station, ' TO ', 1) else station end as a_txt,
    case when station like '% TO %' then split_part(station, ' TO ', 2) end as b_txt
from stg_delays;

-- Match each text once: alias seed, then exact key, then a unique prefix (texts are cut at
-- 22 characters). When the line is known the prefix only has to be unique among that
-- line's stations, so "ST AN" on Line 1 is St Andrew; otherwise it needs 4+ characters.
create temp table text_match as
with t as (
    select distinct txt, line, station_key(txt) as key from (
        select a_txt as txt, line from raw_texts
        union all
        select b_txt, line from raw_texts where b_txt is not null
    )
),
on_line as (
    select t.txt, t.line, any_value(k.station) as station
    from t
    join station_keys k on starts_with(k.key, t.key) and length(t.key) >= 2
    join line_stations ls on ls.station = k.station and ls.line = t.line
    group by t.txt, t.line
    having count(distinct k.station) = 1
),
anywhere as (
    select t.txt, t.line, any_value(k.station) as station
    from t
    join station_keys k on starts_with(k.key, t.key) and length(t.key) >= 4
    where t.line is null or t.line not in (select line from line_stations)
    group by t.txt, t.line
    having count(distinct k.station) = 1
)
select t.txt, t.line, coalesce(a.station, x.station, o.station, w.station) as station
from t
left join seed_station_aliases a on a.key = t.key
left join station_keys x on x.key = t.key
left join on_line o on o.txt = t.txt and o.line is not distinct from t.line
left join anywhere w on w.txt = t.txt and w.line is not distinct from t.line;

-- A stretch counts only if both ends are stations on the delay's own line, so it can be
-- expanded; otherwise (Scarborough RT, cut-off ambiguous ends) it stays unmatched.
create temp table raw_station_match as
select
    r.raw, r.line,
    case when not r.is_stretch then a.station
         when a1.station is not null and b1.station is not null then a.station end as station,
    case when r.is_stretch and a1.station is not null and b1.station is not null then b.station end as station_to
from raw_texts r
left join text_match a on a.txt = r.a_txt and a.line is not distinct from r.line
left join text_match b on b.txt = r.b_txt and b.line is not distinct from r.line
left join line_stations a1 on a1.station = a.station and a1.line = r.line
left join line_stations b1 on b1.station = b.station and b1.line = r.line;

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
    m.station_to,
    p.* exclude (day_date, time_of_day, station)
from parsed p
left join raw_station_match m on m.raw = p.station and m.line is not distinct from p.line
where day_date is not null and time_of_day is not null
order by delay_id;

create table delay_stations as
select d.delay_id, s.station
from subway_delays d
join line_stations a on a.line = d.line and a.station = d.station
join line_stations b on b.line = d.line and b.station = d.station_to
join line_stations s on s.line = d.line and s.seq between least(a.seq, b.seq) and greatest(a.seq, b.seq)
union all
select delay_id, station from subway_delays where station is not null and station_to is null
order by delay_id, station;
