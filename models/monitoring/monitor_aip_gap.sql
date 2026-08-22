-- The outside opinion, in the warehouse instead of on one laptop.
--
-- Every layer we own is downstream of the same MBIE file, so no test we
-- write can catch a stale-but-well-formed source — the 19 Aug 2026 failure
-- passed 60 green tests. The Australian Institute of Petroleum republishes
-- the Argus Singapore product quote that MBIE builds `Importer cost` from,
-- three days ahead of MBIE's Wednesday. Where the two disagree, the ingest
-- is the suspect, not the market.
--
-- The comparison is on the WEEK-ON-WEEK MOVE, never the level. The gap to
-- our landed cost is not constant — diesel's went 6.9 -> 13.4 USD/bbl over
-- Oct 2025 - Aug 2026 while petrol's held at 7.4 - 9.6 — so `markup_usd_bbl`
-- below is reported and never tested against a threshold.
--
-- Flags here are signals with no authority: this model feeds nothing, and its
-- tests warn. See `docs/mbie_notes.md` for what the check can and cannot see.

{% set litres_per_bbl = 158.987 %}

with ours as (

    select
        f.Date,
        f.Fuel,
        f.importer_cost / 100.0 * g.exchange_rate * {{ litres_per_bbl }} as cost_usd_bbl
    from {{ ref('silver_fuel') }} f
    inner join {{ ref('silver_general') }} g
        on f.Date = g.Date

),

paired as (

    -- Inner join on both sides: a week AIP has and we do not is a different
    -- signal, tested separately, and would only mislead as a null row here.
    select
        a.week,
        a.fuel,
        a.product_usd_bbl   as argus_usd_bbl,
        o.cost_usd_bbl      as mbie_usd_bbl
    from {{ ref('aip_singapore_weekly') }} a
    inner join ours o
        on o.Date = a.week
        and o.Fuel = a.fuel

),

moved as (

    select
        week,
        fuel,
        argus_usd_bbl,
        mbie_usd_bbl,
        lag(week)           over (partition by fuel order by week) as prior_week,
        lag(argus_usd_bbl)  over (partition by fuel order by week) as prior_argus,
        lag(mbie_usd_bbl)   over (partition by fuel order by week) as prior_mbie
    from paired

)

select
    week,
    fuel,
    -- AIP has no archive and loses reports after 11-15 weeks, so consecutive
    -- rows here can be months apart. A move across a gap is still a like-for-
    -- like comparison, but it is not a staleness signal, and the tests say so.
    datediff(day, prior_week, week) / 7      as gap_weeks,
    mbie_usd_bbl,
    argus_usd_bbl,
    mbie_usd_bbl - argus_usd_bbl            as markup_usd_bbl,
    mbie_usd_bbl - prior_mbie               as mbie_move,
    argus_usd_bbl - prior_argus             as argus_move,
    case
        when prior_week is null then null
        when abs(argus_usd_bbl - prior_argus) > {{ var('aip_move_threshold_usd') }}
             and abs(mbie_usd_bbl - prior_mbie)
                 < {{ var('aip_damping_ratio') }} * abs(argus_usd_bbl - prior_argus)
            then 'stale_suspected'
        when (mbie_usd_bbl - prior_mbie) * (argus_usd_bbl - prior_argus) < 0
             and abs(mbie_usd_bbl - prior_mbie) > {{ var('aip_move_threshold_usd') }}
             and abs(argus_usd_bbl - prior_argus) > {{ var('aip_move_threshold_usd') }}
            then 'sign_disagreement'
        else null
    end                                     as flag
from moved
