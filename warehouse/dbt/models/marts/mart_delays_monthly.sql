-- Subway delays per month, line, station and cause, for the Tableau delay explorer.
-- station is null where the delay text could not be matched (~9% of rows, see CLAUDE.md).
select
    date_trunc('month', d.occurred_at)::date as month,
    d.line,
    d.station,
    d.code,
    c.description as cause,
    count(*) as delays,
    count(*) filter (where d.min_delay >= 10) as delays_10_plus_min,
    sum(d.min_delay) as total_delay_min,
    median(d.min_delay) as median_delay_min
from {{ ref('subway_delays') }} d
left join {{ ref('delay_codes') }} c using (code)
where d.line in ('1', '2', '3', '4')
group by all
order by all
