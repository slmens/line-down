-- Tables from our own live collectors. Times are converted from UTC to Toronto local
-- time so they line up with the history tables.
-- Inputs: live_station_status, live_ttc_alerts (raw snapshot rows, from build.py).

-- Every station_status snapshot we have: gaps here are gaps in collection.
create table dock_snapshots as
select distinct timezone('America/Toronto', to_timestamp(last_updated)) as observed_at
from live_station_status
order by 1;

-- Bikes and free docks per station, kept only when something changed
-- (most stations are unchanged between 30-second snapshots).
create table dock_status as
with s as (
    select
        try_cast(st.station_id as integer) as station_id,
        timezone('America/Toronto', to_timestamp(last_updated)) as observed_at,
        st.num_bikes_available as bikes,
        st.num_docks_available as docks,
        st.num_bikes_disabled as bikes_disabled,
        st.num_docks_disabled as docks_disabled,
        st.is_renting = 1 as is_renting,
        st.is_returning = 1 as is_returning
    from (select last_updated, unnest(data.stations) as st from live_station_status)
),
w as (
    select *, lag(row(bikes, docks, bikes_disabled, docks_disabled, is_renting, is_returning))
              over (partition by station_id order by observed_at) as prev
    from s
)
select * exclude (prev) from w
where prev is distinct from row(bikes, docks, bikes_disabled, docks_disabled, is_renting, is_returning)
order by station_id, observed_at;

-- One row per alert id: when it first appeared, when it was last seen and when it
-- disappeared (first later snapshot without it; null while still active). The feed's
-- own timestamps are local time mislabelled "Z", so they are kept only as raw text.
create table ttc_alerts as
with snaps as (
    select timezone('America/Toronto', to_timestamp(snapshot_ts)) as seen_at, routes
    from live_ttc_alerts
),
present as (
    select seen_at, unnest(routes) as a from snaps
),
per_alert as (
    select
        a.id as alert_id,
        min(seen_at) as first_seen,
        max(seen_at) as last_seen,
        arg_max(a, seen_at) as latest
    from present
    group by a.id
)
select
    p.alert_id,
    p.first_seen,
    p.last_seen,
    (select min(seen_at) from snaps where seen_at > p.last_seen) as cleared_at,
    p.latest.routeType as route_type,
    p.latest.route as route,
    p.latest.alertType as alert_type,
    p.latest.effect as effect,
    p.latest.stopStart as stop_start,
    p.latest.stopEnd as stop_end,
    p.latest.title as title,
    p.latest.activePeriod.start as active_start_raw,
    p.latest.activePeriod."end" as active_end_raw
from per_alert p
order by first_seen, alert_id;
