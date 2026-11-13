-- from warehouse/sql/30_delays.sql
-- Match each text once: alias seed, then exact key, then a unique prefix (texts are cut at
-- 22 characters). When the line is known the prefix only has to be unique among that
-- line's stations, so "ST AN" on Line 1 is St Andrew; otherwise it needs 4+ characters.
with t as (
    select distinct txt, line, station_key(txt) as key from (
        select a_txt as txt, line from {{ ref('int_raw_texts') }}
        union all
        select b_txt, line from {{ ref('int_raw_texts') }} where b_txt is not null
    )
),
on_line as (
    select t.txt, t.line, any_value(k.station) as station
    from t
    join {{ ref('int_station_keys') }} k on starts_with(k.key, t.key) and length(t.key) >= 2
    join {{ ref('line_stations') }} ls on ls.station = k.station and ls.line = t.line
    group by t.txt, t.line
    having count(distinct k.station) = 1
),
anywhere as (
    select t.txt, t.line, any_value(k.station) as station
    from t
    join {{ ref('int_station_keys') }} k on starts_with(k.key, t.key) and length(t.key) >= 4
    where t.line is null or t.line not in (select line from {{ ref('line_stations') }})
    group by t.txt, t.line
    having count(distinct k.station) = 1
)
select t.txt, t.line, coalesce(a.station, x.station, o.station, w.station) as station
from t
left join {{ ref('station_aliases') }} a on a.key = t.key
left join {{ ref('int_station_keys') }} x on x.key = t.key
left join on_line o on o.txt = t.txt and o.line is not distinct from t.line
left join anywhere w on w.txt = t.txt and w.line is not distinct from t.line
