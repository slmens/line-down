-- from warehouse/sql/20_stations.sql
select
    -- Bloor (Line 1) and Yonge (Line 2) are one interchange.
    case when base in ('Bloor Station', 'Yonge Station') then 'Bloor-Yonge Station' else base end as station,
    -- rounded so parallel summation order cannot change the result between builds (6 dp ~ 10 cm)
    round(avg(lat), 6) as lat,
    round(avg(lon), 6) as lon,
    string_agg(distinct line, ',' order by line) as lines,
    count(*) as platforms
from (select *, regexp_replace(stop_name, ' - .*$', '') as base from {{ ref('subway_platforms') }})
group by 1
order by 1
