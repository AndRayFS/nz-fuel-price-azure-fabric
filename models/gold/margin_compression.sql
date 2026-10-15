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
--
-- THE ADJUSTMENT CAN BE TAKEN OUT FOR 27 FEB – 11 SEP, AND ONLY THEN. MBIE
-- publishes the margin net of it and nothing else. But the 24 Sep load
-- rewrote every week of that stretch, and the snapshot kept the version from
-- before: the margin moved by exactly the adjustment, with cost moving the
-- other way (mbie_notes.md, "Known structural changes", 23 Sep). Weeks after
-- 11 Sep arrived already adjusted and have no unadjusted value anywhere.
--
-- The adjustment is the change AT that load — the version valid on 20 Sep
-- against the one valid on 25 Sep — not the old value against today's, so
-- later revisions (a finalisation, an ordinary correction) stay in the
-- margin and out of the adjustment. One thing cannot be separated: eleven of
-- those weeks were still Provisional on 24 Sep, and an ordinary correction
-- that same day would land in the difference too.
--
-- `margin_before_adjustment` is today's margin with the adjustment added
-- back, and its gap is measured against a norm built the same way, so the
-- two gaps compare like with like.

{{ config(materialized='table') }}

{% set adjustment_from = '2026-02-27' %}
{% set adjustment_known_to = '2026-09-11' %}

with snapshot_at as (
    select
        cast(Date as date)                                      as week_date,
        Fuel                                                    as fuel,
        try_cast(Value as float)                                as value,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('mbie_revisions') }}
    where Variable = 'Importer margin'
),

adjustment as (
    select
        pre.week_date,
        pre.fuel,
        pre.value - post.value                                  as adjustment_cpl
    from snapshot_at pre
    join snapshot_at post
        on post.week_date = pre.week_date
       and post.fuel      = pre.fuel
    -- the last version before the 24 Sep load, and the one it wrote
    where pre.dbt_valid_from  <= '2026-09-20'
      and (pre.dbt_valid_to  > '2026-09-20' or pre.dbt_valid_to is null)
      and post.dbt_valid_from <= '2026-09-25'
      and (post.dbt_valid_to > '2026-09-25' or post.dbt_valid_to is null)
      and pre.week_date between '{{ adjustment_from }}' and '{{ adjustment_known_to }}'
),

series as (
    select
        cast(s.Date as date)                                    as week_date,
        s.Fuel                                                  as fuel,
        s.importer_margin,
        s.importer_margin_status,
        a.adjustment_cpl,
        -- before 27 Feb there was nothing to take out; after 11 Sep it is
        -- unknown, so the series stops rather than pretending it is zero
        case when cast(s.Date as date) <= '{{ adjustment_known_to }}'
             then s.importer_margin + coalesce(a.adjustment_cpl, 0)
        end                                                     as margin_unadjusted
    from {{ ref('silver_fuel') }} s
    left join adjustment a
        on a.week_date = cast(s.Date as date)
       and a.fuel      = s.Fuel
),

margin as (
    select
        *,
        avg(importer_margin) over (
            partition by fuel order by week_date
            rows between 104 preceding and 1 preceding)         as margin_norm_104w,
        -- a full window or nothing: the first weeks of a fuel's series would
        -- otherwise carry a norm built from a handful of rows
        count(importer_margin) over (
            partition by fuel order by week_date
            rows between 104 preceding and 1 preceding)         as norm_weeks,
        avg(margin_unadjusted) over (
            partition by fuel order by week_date
            rows between 104 preceding and 1 preceding)         as norm_unadjusted
    from series
)

select
    m.week_date,
    m.fuel,
    m.importer_margin,
    m.importer_margin_status,
    m.margin_norm_104w,
    100.0 * (m.importer_margin - m.margin_norm_104w)
          / nullif(m.margin_norm_104w, 0)                       as margin_gap_pct,
    cast(case when m.week_date >= '{{ adjustment_from }}' then 1 else 0 end as bit)
                                                                as fuel_market_adjustment,
    case when m.week_date between '{{ adjustment_from }}' and '{{ adjustment_known_to }}'
         then m.adjustment_cpl end                              as adjustment_cpl,
    case when m.week_date between '{{ adjustment_from }}' and '{{ adjustment_known_to }}'
         then m.margin_unadjusted end                           as margin_before_adjustment,
    case when m.week_date between '{{ adjustment_from }}' and '{{ adjustment_known_to }}'
         then 100.0 * (m.margin_unadjusted - m.norm_unadjusted)
                    / nullif(m.norm_unadjusted, 0) end          as gap_before_adjustment_pct,
    f.cost_backfilled
from margin m
-- both keys: period_flags is one row per (week, fuel)
left join {{ source('derived', 'period_flags') }} f
    on f.week_date = m.week_date
   and f.fuel      = m.fuel
where m.week_date >= '2024-03-29'
  and m.norm_weeks = 104
