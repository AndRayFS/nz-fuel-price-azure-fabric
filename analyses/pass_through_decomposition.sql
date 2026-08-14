-- What moves the pump price when crude moves: cost, margin, or neither.
--
-- Splits the cumulative response to a weekly crude move into its published
-- components, separately for crude rises and falls, at four horizons and
-- across structural eras. Response is c/L per NZD/bbl.
--
-- Target construction matters and is not the obvious one:
--   * `board_price - taxes - gst - ets`, NOT `price_excluding_tax`. Both
--     strip the policy-driven drift, but price_excluding_tax is derived
--     from the adjusted series and so inherits the quarterly re-basing
--     steps (169 of 1163 weeks, up to 10.69 c/L). In a differenced series
--     those steps are indistinguishable from real movement.
--   * Removing GST also removes a 15% multiplicative inflation of every
--     response measured on the gross price.
--
-- Four horizons rather than one, because diesel's response peaks around
-- three weeks and petrol's around one: a single window flatters one fuel.
-- Reading any single row as "the" pass-through misses that the numbers
-- keep climbing out to six weeks.
--
-- Ratios of means, not fitted slopes. Crude is rounded to whole dollars
-- (docs/mbie_notes.md), and measurement error biases a slope toward zero,
-- worst where the move is smallest — which manufactured a spurious "small
-- moves don't pass through" finding. A ratio of means is robust to it.
--
-- Results (14 Aug 2026) in docs/architecture.md. Headline: importer margin
-- moves WITH crude in all 32 cells and the amplification grows with
-- horizon; diesel's landed cost is 1.5-2.4x more crude-sensitive than
-- petrol's, but only in the import era; and diesel's up/down asymmetry is
-- already present in the cost, converging to nothing by six weeks.
--
-- Caveats that belong with any number taken from here: horizons overlap,
-- so roughly n/3 observations are independent; and in the pre-2020 era the
-- board-derived target carries ~0.25 of adjustment-factor co-movement with
-- crude, inflating the price response (the import-era residual is zero).

with crude as (
    select
        Date,
        dubai_crude_nzd - lag(dubai_crude_nzd) over (order by Date) as dcrude
    from {{ ref('silver_general') }}
),

tgt as (
    select
        Date, Fuel,
        importer_cost,
        importer_margin,
        board_price - taxes - gst - ets as net_price
    from {{ ref('silver_fuel') }}
    where Fuel in ('Regular Petrol', 'Diesel')
),

h as (
    select 2 as hz union all select 3 union all select 4 union all select 6
),

obs as (
    select
        c.Date, t0.Fuel, h.hz, c.dcrude,
        tn.importer_cost   - t0.importer_cost   as d_cost,
        tn.importer_margin - t0.importer_margin as d_margin,
        tn.net_price       - t0.net_price       as d_net
    from crude c
    cross join h
    join tgt t0 on t0.Date = c.Date
    join tgt tn on tn.Date = dateadd(week, h.hz, c.Date) and tn.Fuel = t0.Fuel
    where c.dcrude is not null
      and c.dcrude <> 0
),

tagged as (
    select
        *,
        -- Boundaries are documented events, not eyeballed: Marsden Point
        -- stopped refining 31 Mar 2022. The transition era is excluded from
        -- reporting — 35-60 observations and COVID whipsaw make it unusable.
        case
            when Date < '2020-03-01' then 'pre_2020'
            when Date < '2022-04-01' then 'transition'
            else 'import_era'
        end as era,
        case when dcrude < 0 then 'down' else 'up' end as direction
    from obs
)

select
    Fuel,
    era,
    hz as horizon_weeks,
    direction,
    count(*) as n,
    round(avg(abs(dcrude)), 2) as avg_crude_move,
    round(avg(d_cost)   / nullif(avg(dcrude), 0), 3) as cost_response,
    round(avg(d_margin) / nullif(avg(dcrude), 0), 3) as margin_response,
    round(avg(d_net)    / nullif(avg(dcrude), 0), 3) as net_price_response,
    round(avg(d_net)    / nullif(avg(d_cost), 0), 2) as price_vs_cost
from tagged
where era <> 'transition'
group by Fuel, era, hz, direction
order by Fuel, era, direction, hz
