-- Expanding-window lag stability, all periods and fuels.
--
-- For every week in every period, recompute the crude→pump correlation at
-- every lag using ONLY data up to that week, then record which lag wins and
-- BY HOW MUCH. The margin of victory (`gap`) is the point of this query:
-- an earlier version recorded only argmax and produced a finding that did
-- not survive contact with the gap — see "Diesel's 'lag shift' was a flat
-- peak" in docs/architecture.md.
--
-- This is an analysis, not a model: it does not run as part of `dbt run`.
-- Compile it (`dbt compile -s lag_stability_expanding_window`) and execute
-- target/compiled/.../lag_stability_expanding_window.sql against the
-- warehouse. The permanent model on the roadmap (roadmap item 1) narrows
-- this to the open period.
--
-- Two knobs that materially change the answer:
--   * max_lag rule. Below is the honest as-of rule (`weeks_so_far // 3`,
--     matching lag_correlation), so a lag only enters the search once the
--     period is long enough. That makes a lag's first appearance look like
--     a transition — hence `max_lag_allowed` and `cap_lifted_this_week`
--     in the output. A fixed cap makes weeks comparable instead. Do not mix.
--   * min n. Filtered to n >= 6 at the end; below that the search is noise.

with p as (
    select
        period_id,
        period_name,
        period_type,
        start_date,
        coalesce(end_date, cast(getdate() as date)) as end_date
    from {{ ref('periods') }}
),

l as (
    select 0 as lag_weeks union all select 1 union all select 2 union all select 3
    union all select 4 union all select 5 union all select 6 union all select 7
    union all select 8 union all select 9 union all select 10
),

-- One cutoff per observation date in the period: "if today were this week".
cut as (
    select p.period_id, g.Date as cutoff_date
    from p
    join {{ ref('silver_general') }} g
        on g.Date between p.start_date and p.end_date
),

-- Both sides bounded by the cutoff. Bounding only the factor is the bug
-- documented under "Bug: target wasn't bounded by the period".
pairs as (
    select
        c.period_id,
        c.cutoff_date,
        f.Fuel,
        l.lag_weeks,
        g.dubai_crude_nzd as x,
        f.board_price as y
    from cut c
    join p on p.period_id = c.period_id
    cross join l
    join {{ ref('silver_general') }} g
        on g.Date between p.start_date and c.cutoff_date
       and g.dubai_crude_nzd is not null
    join {{ ref('silver_fuel') }} f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between p.start_date and c.cutoff_date
       and f.board_price is not null
),

stats as (
    select
        period_id, cutoff_date, Fuel, lag_weeks,
        count(*) as n,
        sum(x) as sx, sum(y) as sy,
        sum(x*y) as sxy, sum(x*x) as sxx, sum(y*y) as syy
    from pairs
    group by period_id, cutoff_date, Fuel, lag_weeks
),

corr as (
    select
        period_id, cutoff_date, Fuel, lag_weeks, n,
        case
            when n < 3 then null
            when (n*sxx - sx*sx) <= 0 or (n*syy - sy*sy) <= 0 then null
            else (n*sxy - sx*sy) / sqrt((n*sxx - sx*sx) * (n*syy - sy*sy))
        end as r
    from stats
),

with_cap as (
    select
        c.*,
        p.period_name,
        p.period_type,
        datediff(day, p.start_date, c.cutoff_date) / 7 as weeks_so_far,
        case
            when datediff(day, p.start_date, c.cutoff_date) / 7 / 3 < 10
            then datediff(day, p.start_date, c.cutoff_date) / 7 / 3
            else 10
        end as max_lag_allowed
    from corr c
    join p on p.period_id = c.period_id
    where c.r is not null
),

eligible as (
    select * from with_cap where lag_weeks <= max_lag_allowed
),

ranked as (
    select
        *,
        row_number() over (
            partition by period_id, Fuel, cutoff_date order by r desc
        ) as rn
    from eligible
),

best as (
    select
        b.period_id, b.period_name, b.period_type, b.Fuel, b.cutoff_date,
        b.weeks_so_far, b.max_lag_allowed, b.n,
        b.lag_weeks as best_lag,
        b.r as best_r,
        s.lag_weeks as second_lag,
        s.r as second_r,
        b.r - s.r as gap
    from ranked b
    left join ranked s
        on s.period_id = b.period_id
       and s.Fuel = b.Fuel
       and s.cutoff_date = b.cutoff_date
       and s.rn = 2
    where b.rn = 1
),

seq as (
    select
        *,
        lag(best_lag) over (
            partition by period_id, Fuel order by cutoff_date
        ) as prev_lag,
        lag(max_lag_allowed) over (
            partition by period_id, Fuel order by cutoff_date
        ) as prev_max_lag_allowed
    from best
    where n >= 6
)

select
    period_id,
    period_name,
    period_type,
    Fuel,
    cutoff_date,
    n,
    weeks_so_far,
    max_lag_allowed,
    best_lag,
    best_r,
    second_lag,
    second_r,
    gap,
    case when prev_lag is not null and best_lag <> prev_lag then 1 else 0 end
        as lag_changed,
    -- A "change" the week the ceiling rises is the search space growing,
    -- not the data moving. Excluded from any stability signal.
    case
        when prev_lag is not null
         and best_lag <> prev_lag
         and max_lag_allowed > prev_max_lag_allowed
         and best_lag > prev_max_lag_allowed
        then 1 else 0
    end as cap_lifted_this_week
from seq
order by period_id, Fuel, cutoff_date
