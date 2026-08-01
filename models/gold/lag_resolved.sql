{{ config(materialized='table') }}

with ranked as (
    select
        period_id, period_name, period_type, factor, target, fuel,
        lag_weeks, n, r,
        row_number() over (
            partition by period_id, factor, target, fuel
            order by r desc
        ) as rn,
        max(lag_weeks) over (partition by period_id, factor, target, fuel) as max_lag_tested
    from {{ ref('lag_correlation') }}
    where r is not null
),

best_row as (
    select * from ranked where rn = 1
),

neighbor as (
    select lc.period_id, lc.factor, lc.target, lc.fuel, lc.r as r_at_edge_minus_1
    from {{ ref('lag_correlation') }} lc
    inner join best_row b
        on lc.period_id = b.period_id
        and lc.factor = b.factor
        and lc.target = b.target
        and lc.fuel = b.fuel
        and lc.lag_weeks = b.max_lag_tested - 1
),

zero_lag as (
    select period_id, factor, target, fuel, r as r_at_zero
    from {{ ref('lag_correlation') }}
    where lag_weeks = 0
)

select
    b.period_id,
    b.period_name,
    b.period_type,
    b.factor,
    b.target,
    b.fuel,
    b.lag_weeks as raw_best_lag,
    b.r as raw_best_r,
    case
        when b.lag_weeks = b.max_lag_tested
             and nb.r_at_edge_minus_1 is not null
             and b.r > nb.r_at_edge_minus_1
        then 1 else 0
    end as is_edge_artifact,
    case
        when b.lag_weeks = b.max_lag_tested
             and nb.r_at_edge_minus_1 is not null
             and b.r > nb.r_at_edge_minus_1
        then 0
        else b.lag_weeks
    end as resolved_lag,
    case
        when b.lag_weeks = b.max_lag_tested
             and nb.r_at_edge_minus_1 is not null
             and b.r > nb.r_at_edge_minus_1
        then z.r_at_zero
        else b.r
    end as resolved_r
from best_row b
left join neighbor nb
    on nb.period_id = b.period_id and nb.factor = b.factor and nb.target = b.target and nb.fuel = b.fuel
left join zero_lag z
    on z.period_id = b.period_id and z.factor = b.factor and z.target = b.target and z.fuel = b.fuel
order by b.period_id, b.factor, b.target, b.fuel
