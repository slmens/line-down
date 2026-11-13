-- from warehouse/sql/30_delays.sql
-- A stretch counts only if both ends are stations on the delay's own line, so it can be
-- expanded; otherwise (Scarborough RT, cut-off ambiguous ends) it stays unmatched.
select
    r.raw, r.line,
    case when not r.is_stretch then a.station
         when a1.station is not null and b1.station is not null then a.station end as station,
    case when r.is_stretch and a1.station is not null and b1.station is not null then b.station end as station_to
from {{ ref('int_raw_texts') }} r
left join {{ ref('int_text_match') }} a on a.txt = r.a_txt and a.line is not distinct from r.line
left join {{ ref('int_text_match') }} b on b.txt = r.b_txt and b.line is not distinct from r.line
left join {{ ref('line_stations') }} a1 on a1.station = a.station and a1.line = r.line
left join {{ ref('line_stations') }} b1 on b1.station = b.station and b1.line = r.line
