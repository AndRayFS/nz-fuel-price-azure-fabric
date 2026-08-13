-- Levels vs week-over-week changes: same lag search, two bases.
--
-- The project has always correlated LEVELS — lag_correlation_series feeds
-- raw dubai_crude_nzd and board_price into the sums, inherited from the
-- original R script. Crude's within-window correlation with time averages
-- 0.57-0.66 across the full history, so every level-based estimate carries
-- some shared drift. Differencing both series removes it and asks the
-- narrower question the project actually cares about: when crude moved,
-- how many weeks later did the pump price move?
--
-- Result (13 Aug 2026, 26-week windows): on changes the peak is ~5x better
-- separated from the runner-up (gap 0.149 vs 0.031) while r drops ~0.23.
-- That is the signature of a real timing relationship rather than a trend
-- artifact — if the lag were an artifact, differencing would leave nothing.
--
-- Read the per-lag SLOPES with care: each is a separate univariate
-- regression, and weekly crude changes are autocorrelated, so neighbouring
-- lags all claim the same market move. They are comparable in SHAPE across
-- fuels but must NOT be summed into distributed-lag weights — diesel's lags
-- 0-4 sum to 2.22 against a levels slope of 0.98. Real weights need one
-- joint regression on all lags at once. See docs/architecture.md.
--
-- Window width is a parameter, not a constant of nature: the share of
-- decisive windows runs 44-48% at 13 weeks, 16-18% at 26 and 5-9% at 52.
-- Report it with any figure derived here.

{% set window_weeks = 26 %}
{% set max_lag = (window_weeks / 3) | int %}

with bounds as (
    select min(Date) as first_date from {{ ref('silver_general') }}
),

w as (
    select
        g.Date as w_end,
        dateadd(week, -{{ window_weeks - 1 }}, g.Date) as w_start
    from {{ ref('silver_general') }} g
    cross join bounds b
    where g.Date >= dateadd(week, {{ window_weeks - 1 }}, b.first_date)
),

l as (
    select 0 as lag_weeks
    {% for i in range(1, max_lag + 1) %}
    union all select {{ i }}
    {% endfor %}
),

-- Both bases built once, here, so the arithmetic below is identical for
-- each and any difference in the result is the basis alone.
gen as (
    select
        Date,
        dubai_crude_nzd as lvl,
        dubai_crude_nzd - lag(dubai_crude_nzd) over (order by Date) as chg
    from {{ ref('silver_general') }}
),

fuel as (
    select
        Date, Fuel,
        board_price as lvl,
        board_price - lag(board_price) over (partition by Fuel order by Date) as chg
    from {{ ref('silver_fuel') }}
),

pairs as (
    select 'levels' as basis, w.w_end, f.Fuel, l.lag_weeks, g.lvl as x, f.lvl as y
    from w
    cross join l
    join gen g on g.Date between w.w_start and w.w_end
    join fuel f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between w.w_start and w.w_end

    union all

    select 'changes', w.w_end, f.Fuel, l.lag_weeks, g.chg, f.chg
    from w
    cross join l
    join gen g
        on g.Date between w.w_start and w.w_end
       and g.chg is not null
    join fuel f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between w.w_start and w.w_end
       and f.chg is not null
),

stats as (
    select
        basis, w_end, Fuel, lag_weeks,
        count(*) as n,
        sum(x) as sx, sum(y) as sy,
        sum(x*y) as sxy, sum(x*x) as sxx, sum(y*y) as syy
    from pairs
    group by basis, w_end, Fuel, lag_weeks
),

corr as (
    select
        basis, w_end, Fuel, lag_weeks, n,
        case
            when n < 3 then null
            when (n*sxx - sx*sx) <= 0 or (n*syy - sy*sy) <= 0 then null
            else (n*sxy - sx*sy) / sqrt((n*sxx - sx*sx) * (n*syy - sy*sy))
        end as r,
        case
            when n < 3 then null
            when (n*sxx - sx*sx) <= 0 then null
            else (n*sxy - sx*sy) / (n*sxx - sx*sx)
        end as slope
    from stats
),

ranked as (
    select
        *,
        row_number() over (partition by basis, w_end, Fuel order by r desc) as rn,
        max(r) over (partition by basis, w_end, Fuel) as r_max,
        min(r) over (partition by basis, w_end, Fuel) as r_min
    from corr
    where r is not null
)

select
    b.basis,
    b.w_end,
    b.Fuel,
    b.n,
    b.lag_weeks as best_lag,
    b.r as best_r,
    b.slope as slope_at_best,
    s.lag_weeks as second_lag,
    b.r - s.r as gap,
    abs(b.lag_weeks - s.lag_weeks) as dist_to_second,
    -- Range across every lag. Near zero with a high r_max means a trend
    -- plateau, not a relationship: a straight line correlates with itself
    -- equally well at any shift.
    b.r_max - b.r_min as r_range
from ranked b
left join ranked s
    on s.basis = b.basis and s.w_end = b.w_end and s.Fuel = b.Fuel and s.rn = 2
where b.rn = 1
order by b.Fuel, b.basis, b.w_end
