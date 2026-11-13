-- from warehouse/sql/30_delays.sql
select d.delay_id, s.station
from {{ ref('subway_delays') }} d
join {{ ref('line_stations') }} a on a.line = d.line and a.station = d.station
join {{ ref('line_stations') }} b on b.line = d.line and b.station = d.station_to
join {{ ref('line_stations') }} s on s.line = d.line and s.seq between least(a.seq, b.seq) and greatest(a.seq, b.seq)
union all
select delay_id, station from {{ ref('subway_delays') }} where station is not null and station_to is null
order by delay_id, station
