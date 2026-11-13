-- from warehouse/sql/40_live.sql
-- One row per alert id: when it first appeared, when it was last seen and when it
-- disappeared (first later snapshot without it; null while still active). The feed's
-- own timestamps are local time mislabelled "Z", so they are kept only as raw text.
with snaps as (
    select timezone('America/Toronto', to_timestamp(snapshot_ts)) as seen_at, routes
    from {{ source('staging', 'live_ttc_alerts') }}
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
order by first_seen, alert_id
