{{ config(materialized='table') }}

{% set window_weeks = var('volatility_window_weeks', 6) %}

with pct_changes as (
    select
        Date,
        dubai_crude_nzd,
        (dubai_crude_nzd - lag(dubai_crude_nzd) over (order by Date))
            / lag(dubai_crude_nzd) over (order by Date) as pct_change
    from {{ ref('silver_general') }}
),

calm_baseline_calc as (
    select stdev(pc.pct_change) as calm_baseline
    from pct_changes pc
    inner join {{ ref('periods') }} p
        on pc.Date >= p.start_date
        and pc.Date <= coalesce(p.end_date, cast(getdate() as date))
    where p.period_type = 'calm'
)

select
    pc.Date,
    pc.pct_change,
    stdev(pc.pct_change) over (
        order by pc.Date
        rows between {{ window_weeks - 1 }} preceding and current row
    ) as rolling_volatility,
    cb.calm_baseline
from pct_changes pc
cross join calm_baseline_calc cb
order by pc.Date
