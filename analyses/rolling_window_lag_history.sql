-- Rolling-window lag search over the full 2004-2026 history.
--
-- Everything else in this project measures lag inside hand-picked periods
-- from the `periods` seed. That seed is a hypothesis, so this query drops it
-- and sweeps a fixed 26-week window across all 1164 weeks instead, one week
-- at a time.
--
-- Why 26 weeks and lags 0-8: the project's own cap rule is `weeks // 3`,
-- which for a 26-week window is 8. Evaluating it once gives a CONSTANT
-- ceiling across every window, so the "a lag became newly testable" artifact
-- documented in docs/architecture.md cannot occur here.
--
-- Headline result (13 Aug 2026): the winning lag beats the runner-up by
-- >= 0.05 in only 14-20% of windows. Ties are the normal case across the
-- whole history, not a diesel-in-2026 quirk — which is the argument for a
-- distributed lag model over picking one "best" lag.
--
-- Two things this design cannot do, both load-bearing:
--   * Overlapping windows are not independent observations. 26-week windows
--     stepped weekly give roughly n/26 independent looks, so do not read the
--     window counts as a sample size.
--   * It cannot separate events closer together than the window width. The
--     Envisory -> Datamine retail price switch (1 Jan 2022) and the Marsden
--     Point refining shutdown (31 Mar 2022) are 13 weeks apart and therefore
--     inseparable here. See docs/mbie_notes.md.
--
-- Output is one row per (window end, fuel); aggregate it by year or by era
-- as needed.

with bounds as (
    select min(Date) as first_date from {{ ref('silver_general') }}
),

w as (
    select
        g.Date as w_end,
        dateadd(week, -25, g.Date) as w_start
    from {{ ref('silver_general') }} g
    cross join bounds b
    where g.Date >= dateadd(week, 25, b.first_date)
),

l as (
    select 0 as lag_weeks union all select 1 union all select 2 union all select 3
    union all select 4 union all select 5 union all select 6 union all select 7
    union all select 8
),

-- Both factor and target bounded by the window, matching lag_correlation.
-- Consequence: n shrinks as the lag grows. Kept for comparability.
pairs as (
    select
        w.w_end, w.w_start, f.Fuel, l.lag_weeks,
        g.dubai_crude_nzd as x, f.board_price as y
    from w
    cross join l
    join {{ ref('silver_general') }} g
        on g.Date between w.w_start and w.w_end
    join {{ ref('silver_fuel') }} f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between w.w_start and w.w_end
),

stats as (
    select
        w_end, w_start, Fuel, lag_weeks,
        count(*) as n,
        sum(x) as sx, sum(y) as sy,
        sum(x*y) as sxy, sum(x*x) as sxx, sum(y*y) as syy
    from pairs
    group by w_end, w_start, Fuel, lag_weeks
),

corr as (
    select
        w_end, w_start, Fuel, lag_weeks, n,
        case
            when n < 3 then null
            when (n*sxx - sx*sx) <= 0 or (n*syy - sy*sy) <= 0 then null
            else (n*sxy - sx*sy) / sqrt((n*sxx - sx*sx) * (n*syy - sy*sy))
        end as r
    from stats
),

ranked as (
    select
        *,
        row_number() over (partition by w_end, Fuel order by r desc) as rn
    from corr
    where r is not null
),

crude_var as (
    select
        w.w_end,
        100.0 * stdev(g.dubai_crude_nzd) / avg(g.dubai_crude_nzd) as crude_cv_pct
    from w
    join {{ ref('silver_general') }} g
        on g.Date between w.w_start and w.w_end
    group by w.w_end
)

select
    b.w_start,
    b.w_end,
    b.Fuel,
    b.n,
    b.lag_weeks as best_lag,
    b.r as best_r,
    s.lag_weeks as second_lag,
    b.r - s.r as gap,
    -- Guard against reading a low r as a weakened relationship: correlation
    -- collapses when the factor barely moves. Always check this alongside r.
    cv.crude_cv_pct
from ranked b
left join ranked s
    on s.w_end = b.w_end and s.Fuel = b.Fuel and s.rn = 2
join crude_var cv
    on cv.w_end = b.w_end
where b.rn = 1
order by b.Fuel, b.w_end
