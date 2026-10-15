-- Report 1's margin page: how far each fuel's importer margin sits from its
-- own recent normal, week by week.
--
-- The measure is research.md's ("What the record says after a margin
-- compression", research/margin_episodes.py), carried over unchanged:
--
--   * the norm is the margin's mean over the 104 weeks BEFORE the week —
--     lagged one, so a deep week never drags its own benchmark toward it;
--   * the gap is a share of that norm, not cents. The margin's level has
--     roughly tripled since 2004, so −10 c/L is a different event in each
--     decade. Gaps below −100% are real: the margin itself went negative.
--
-- Rows define the window, as in the pandas rolling() this replaces — silver
-- has one row per (week, fuel) and no gaps.
--
-- From 29 Mar 2024 only: the first week whose whole window falls after
-- Marsden Point closed (1 Apr 2022) and after MBIE's retail source changed
-- (1 Jan 2022). Earlier weeks are left out rather than judged against a norm
-- from an industry that no longer exists.
--
-- Two things a reader must be told travel as columns, so the downloaded file
-- says them too:
--   * `fuel_market_adjustment` — from 27 Feb 2026 MBIE counts a cost
--     adjustment in `Importer cost` and takes it out of the margin (made on
--     23 Sep 2026, applied backwards; mbie_notes.md). After that date the
--     margin is not quite the quantity it was before.
--   * `cost_backfilled` — MBIE suspended cost and margin 18 Mar – 1 Jul 2026
--     and filled them in later. From period_flags, where that rule lives.

{{ config(materialized='table') }}

with margin as (
    select
        cast(Date as date)                                      as week_date,
        Fuel                                                    as fuel,
        importer_margin,
        importer_margin_status,
        avg(importer_margin) over (
            partition by Fuel order by cast(Date as date)
            rows between 104 preceding and 1 preceding)         as margin_norm_104w,
        -- a full window or nothing: the first weeks of a fuel's series would
        -- otherwise carry a norm built from a handful of rows
        count(importer_margin) over (
            partition by Fuel order by cast(Date as date)
            rows between 104 preceding and 1 preceding)         as norm_weeks
    from {{ ref('silver_fuel') }}
)

select
    m.week_date,
    m.fuel,
    m.importer_margin,
    m.importer_margin_status,
    m.margin_norm_104w,
    100.0 * (m.importer_margin - m.margin_norm_104w)
          / nullif(m.margin_norm_104w, 0)                       as margin_gap_pct,
    cast(case when m.week_date >= '2026-02-27' then 1 else 0 end as bit)
                                                                as fuel_market_adjustment,
    f.cost_backfilled
from margin m
-- both keys: period_flags is one row per (week, fuel)
left join {{ source('derived', 'period_flags') }} f
    on f.week_date = m.week_date
   and f.fuel      = m.fuel
where m.week_date >= '2024-03-29'
  and m.norm_weeks = 104
