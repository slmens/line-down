-- from warehouse/sql/30_delays.sql
-- Each distinct (raw text, line). "X TO Y" is a stretch: split into its two ends.
select distinct
    station as raw,
    subway_line(line) as line,
    station like '% TO %' as is_stretch,
    case when station like '% TO %' then split_part(station, ' TO ', 1) else station end as a_txt,
    case when station like '% TO %' then split_part(station, ' TO ', 2) end as b_txt
from {{ source('staging', 'stg_delays') }}
