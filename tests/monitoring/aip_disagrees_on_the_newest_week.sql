-- Warns when the newest week we share with AIP carries a flag: our cost barely
-- moved while Argus moved, or the two moved in opposite directions. This is the
-- shape the 19 Aug 2026 stale ingest made, and the only check in the project
-- that can see it — everything else we test is downstream of the same MBIE file.
--
-- Restricted to the newest shared week per fuel and to `gap_weeks = 1`. Older
-- flags stay visible in the model; a flag across a multi-week gap (AIP deletes
-- its own back catalogue) says nothing about whether this week's ingest was
-- fresh.
{{ config(severity='warn') }}

with newest as (

    select fuel, max(week) as week
    from {{ ref('monitor_aip_gap') }}
    group by fuel

)

select g.week, g.fuel, g.mbie_move, g.argus_move, g.markup_usd_bbl, g.flag
from {{ ref('monitor_aip_gap') }} g
inner join newest n
    on n.fuel = g.fuel
    and n.week = g.week
where g.flag is not null
  and g.gap_weeks = 1
