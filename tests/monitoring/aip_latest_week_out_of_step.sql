-- Warns when the two sides stop ending on the same week, in any of three
-- ways. All are failures of collection, not of the market, and which one it is
-- decides who to go and look at:
--
--   ingest_behind -- AIP already carries a week our own data stops short of.
--     Between AIP's Sunday and MBIE's Wednesday this is normal and means
--     nothing; run after the weekly ingest, it means the ingest did not bring
--     the week in. This is the 19 Aug 2026 failure, seen from outside.
--   aip_store_behind -- our data has moved on and the store has not, so
--     `research/aip_check.py` did not run, or parsed nothing because the PDF
--     was restyled. The comparison is quietly running on old weeks.
--   aip_store_empty -- the store holds nothing for that fuel at all. The
--     expected fuels are listed here rather than read from the store,
--     precisely so that an empty store is loud instead of vacuously fine:
--     grouping the store by fuel returns no rows to compare, and every other
--     check in the AIP half then passes by having nothing to look at.
--
-- None of them stops anything: the run's only stopping point is the freshness
-- gate.
{{ config(severity='warn') }}

with expected as (

    select 'Diesel' as fuel
    union all
    select 'Regular Petrol'

),

ours as (

    select max(Date) as latest_week
    from {{ ref('silver_fuel') }}

),

theirs as (

    select fuel, max(week) as latest_week
    from {{ ref('aip_singapore_weekly') }}
    group by fuel

)

select
    e.fuel,
    t.latest_week       as aip_latest_week,
    o.latest_week       as our_latest_week,
    case
        when t.latest_week is null              then 'aip_store_empty'
        when t.latest_week > o.latest_week      then 'ingest_behind'
        else                                         'aip_store_behind'
    end                 as diagnosis
from expected e
cross join ours o
left join theirs t
    on t.fuel = e.fuel
where t.latest_week is null
   or t.latest_week <> o.latest_week
