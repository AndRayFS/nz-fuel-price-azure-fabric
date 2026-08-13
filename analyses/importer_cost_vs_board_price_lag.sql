-- Does crude land on the modelled landed cost or on the pump price first?
--
-- Same lag search as lag_correlation, run twice per period/fuel: once
-- against `board_price` (what the project normally uses) and once against
-- `importer_cost`. Reports both best lags side by side with each one's
-- margin of victory over the runner-up.
--
-- Result (13 Aug 2026): importer_cost peaks at lag 0 in 15 of 18
-- period/fuel combinations with a much sharper peak than board_price. That
-- is a property of MBIE's construction, not of the market — importer_cost
-- is this week's Singapore product spot at this week's exchange rate, with
-- no purchase date or voyage time in it. See "How `Importer cost` is
-- actually built" in docs/mbie_notes.md before drawing conclusions about
-- shipping time versus pricing behaviour: this dataset cannot separate them.
--
-- Guard against reading r differences across periods as structural change:
-- correlation collapses when the factor's spread narrows. Check crude's CV
-- per period first (table in docs/architecture.md) — that is what killed
-- the refinery-era hypothesis.

with p as (
    select
        period_id,
        period_type,
        start_date,
        coalesce(end_date, cast(getdate() as date)) as end_date,
        case
            when datediff(day, start_date, coalesce(end_date, cast(getdate() as date))) / 7 / 3 < 10
            then datediff(day, start_date, coalesce(end_date, cast(getdate() as date))) / 7 / 3
            else 10
        end as max_lag
    from {{ ref('periods') }}
),

l as (
    select 0 as lag_weeks union all select 1 union all select 2 union all select 3
    union all select 4 union all select 5 union all select 6 union all select 7
    union all select 8 union all select 9 union all select 10
),

pairs as (
    select
        p.period_id, f.Fuel, l.lag_weeks, 'board_price' as target,
        g.dubai_crude_nzd as x, f.board_price as y
    from p
    cross join l
    join {{ ref('silver_general') }} g
        on g.Date between p.start_date and p.end_date
       and g.dubai_crude_nzd is not null
    join {{ ref('silver_fuel') }} f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between p.start_date and p.end_date
       and f.board_price is not null
    where l.lag_weeks <= p.max_lag

    union all

    select
        p.period_id, f.Fuel, l.lag_weeks, 'importer_cost' as target,
        g.dubai_crude_nzd as x, f.importer_cost as y
    from p
    cross join l
    join {{ ref('silver_general') }} g
        on g.Date between p.start_date and p.end_date
       and g.dubai_crude_nzd is not null
    join {{ ref('silver_fuel') }} f
        on f.Date = dateadd(week, l.lag_weeks, g.Date)
       and f.Date between p.start_date and p.end_date
       and f.importer_cost is not null
    where l.lag_weeks <= p.max_lag
),

stats as (
    select
        period_id, Fuel, target, lag_weeks,
        count(*) as n,
        sum(x) as sx, sum(y) as sy,
        sum(x*y) as sxy, sum(x*x) as sxx, sum(y*y) as syy
    from pairs
    group by period_id, Fuel, target, lag_weeks
),

corr as (
    select
        period_id, Fuel, target, lag_weeks, n,
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
        row_number() over (
            partition by period_id, Fuel, target order by r desc
        ) as rn
    from corr
    where r is not null
),

best as (
    select
        b.period_id, b.Fuel, b.target, b.n,
        b.lag_weeks as best_lag,
        b.r as best_r,
        b.r - s.r as gap
    from ranked b
    left join ranked s
        on s.period_id = b.period_id
       and s.Fuel = b.Fuel
       and s.target = b.target
       and s.rn = 2
    where b.rn = 1
)

select
    c.period_id,
    c.Fuel,
    c.n,
    b.best_lag as lag_board,
    b.best_r as r_board,
    b.gap as gap_board,
    c.best_lag as lag_cost,
    c.best_r as r_cost,
    c.gap as gap_cost,
    c.best_r - b.best_r as r_gain
from best c
left join best b
    on b.period_id = c.period_id
   and b.Fuel = c.Fuel
   and b.target = 'board_price'
where c.target = 'importer_cost'
order by c.period_id, c.Fuel
