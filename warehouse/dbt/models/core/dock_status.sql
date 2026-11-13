-- from warehouse/sql/40_live.sql
-- Bikes and free docks per station, kept only when something changed
-- (most stations are unchanged between 30-second snapshots).
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
    from (select last_updated, unnest(data.stations) as st from {{ source('staging', 'live_station_status') }})
),
w as (
    select *, lag(row(bikes, docks, bikes_disabled, docks_disabled, is_renting, is_returning))
              over (partition by station_id order by observed_at) as prev
    from s
)
select * exclude (prev) from w
where prev is distinct from row(bikes, docks, bikes_disabled, docks_disabled, is_renting, is_returning)
order by station_id, observed_at
