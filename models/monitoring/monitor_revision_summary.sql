-- The weekly read: how many weeks changed in each snapshot run, and in which
-- variables. One row per (run, variable, unit, kind of change) — the detail
-- sits in `monitor_revisions` and is only needed once this says something
-- happened.
--
-- `detected_on` is the snapshot run that noticed the change, not the week the
-- number belongs to; `earliest_week` / `latest_week` say how far back the run
-- reached.

select
    detected_on,
    Variable,
    Unit,
    revision_class,
    count(*)                as rows_changed,
    count(distinct Week)    as weeks_changed,
    count(distinct Fuel)    as fuels_affected,
    min(Date)               as earliest_week,
    max(Date)               as latest_week,
    min(value_delta)        as min_delta,
    max(value_delta)        as max_delta
from {{ ref('monitor_revisions') }}
group by detected_on, Variable, Unit, revision_class
