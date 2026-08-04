{{ config(materialized='table') }}

{% set window_weeks = var('volatility_window_weeks', 6) %}

with calm_baseline_calc as (
    select stdev(pc.pct_change) as calm_baseline
    from (
        select
            Date,
            (dubai_crude_nzd - lag(dubai_crude_nzd) over (order by Date))
                / lag(dubai_crude_nzd) over (order by Date) as pct_change
        from {{ ref('silver_general') }}
    ) pc
    inner join {{ ref('periods') }} p
        on pc.Date >= p.start_date
        and pc.Date <= coalesce(p.end_date, cast(getdate() as date))
    where p.period_type = 'calm'
)

select
    {{ window_weeks }} as window_weeks,
    {{ window_weeks * 7 }} as window_days,
    calm_baseline
from calm_baseline_calc
