-- GTFS lists 70 subway stations once Bloor and Yonge are merged; anything else means the
-- station grouping or the GTFS file changed.
select count(*) as n from {{ ref('subway_stations') }} having count(*) <> 70
