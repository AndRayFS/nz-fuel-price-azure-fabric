{{ config(materialized='table') }}

{% set window_weeks = var('volatility_window_weeks', 6) %}

with pct_changes as (
    select
        Date,
        dubai_crude_nzd,
        (dubai_crude_nzd - lag(dubai_crude_nzd) over (order by Date))
            / lag(dubai_crude_nzd) over (order by Date) as pct_change
    from {{ ref('silver_general') }}
)
select
    Date,
    pct_change,
    stdev(pct_change) over (
        order by Date
        rows between {{ window_weeks - 1 }} preceding and current row
    ) as rolling_volatility
from pct_changes
