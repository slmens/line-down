-- Bikes and free docks within 500 m of each subway station at the top of every hour we
-- collected, for the Tableau live-docks dashboard. dock_status only keeps changes, so each
-- dock's level at an hour is its latest change at or before it.
with hours as (
    select distinct date_trunc('hour', observed_at) + interval 1 hour as at_hour
    from {{ ref('dock_snapshots') }}
),
nearby as (
    select s.station, b.station_id,
        -- haversine, metres
        2 * 6371000 * asin(sqrt(
            pow(sin(radians(b.lat - s.lat) / 2), 2)
            + cos(radians(s.lat)) * cos(radians(b.lat)) * pow(sin(radians(b.lon - s.lon) / 2), 2))) as metres
    from {{ ref('subway_stations') }} s
    cross join {{ ref('bike_stations') }} b
),
grid as (
    select h.at_hour, n.station_id from hours h cross join (select distinct station_id from nearby where metres <= 500) n
),
levels as (
    select g.at_hour, g.station_id, d.bikes, d.docks
    from grid g
    asof join {{ ref('dock_status') }} d on d.station_id = g.station_id and d.observed_at <= g.at_hour
)
select
    l.at_hour,
    n.station,
    count(*) as docks_reporting,
    sum(l.bikes) as bikes,
    sum(l.docks) as free_docks,
    count(*) filter (where l.bikes <= 2) as docks_with_2_or_fewer_bikes
from levels l
join nearby n on n.station_id = l.station_id and n.metres <= 500
-- the last hour is not over yet
where l.at_hour <= (select max(observed_at) from {{ ref('dock_snapshots') }})
group by all
order by all
