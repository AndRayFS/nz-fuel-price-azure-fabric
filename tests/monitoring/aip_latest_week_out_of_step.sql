-- Warns when the two sides stop ending on the same week, in either direction.
-- Both are failures of collection, not of the market, and which one it is
-- decides who to go and look at:
--
--   ingest_behind -- AIP already carries a week our own data stops short of.
--     Between AIP's Sunday and MBIE's Wednesday this is normal and means
--     nothing; run after the weekly ingest, it means the ingest did not bring
--     the week in. This is the 19 Aug 2026 failure, seen from outside.
--   aip_store_behind -- our data has moved on and the store has not, so
--     `research/aip_check.py` did not run, or parsed nothing because the PDF
--     was restyled. The comparison is quietly running on old weeks.
--
-- Neither stops anything: the run's only stopping point is the freshness gate.
{{ config(severity='warn') }}

with ours as (

    select max(Date) as latest_week
    from {{ ref('silver_fuel') }}

),

theirs as (

    select fuel, max(week) as latest_week
    from {{ ref('aip_singapore_weekly') }}
    group by fuel

)

select
    theirs.fuel,
    theirs.latest_week  as aip_latest_week,
    ours.latest_week    as our_latest_week,
    case
        when theirs.latest_week > ours.latest_week then 'ingest_behind'
        else 'aip_store_behind'
    end                 as diagnosis
from theirs
cross join ours
where theirs.latest_week <> ours.latest_week
