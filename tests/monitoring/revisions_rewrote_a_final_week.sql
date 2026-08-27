-- Warns when the most recent snapshot run changed a value on a week MBIE had
-- already called Final. Provisional -> Final is routine and is not reported
-- here; a Final number moving is history changing under a report whose whole
-- subject is what the model got wrong at the time.
--
-- Only the newest run is examined, so a revision is raised once, in the week it
-- is noticed.
{{ config(severity='warn') }}

select
    detected_on,
    Date,
    Fuel,
    Variable,
    Unit,
    prior_value,
    new_value,
    value_delta
from {{ ref('monitor_revisions') }}
where revision_class = 'final_rewritten'
  and detected_on = (select max(detected_on) from {{ ref('monitor_revisions') }})
  -- A change too small to be a decision about the number is a change to how it
  -- is written down. Scoped to c/L because the threshold is a c/L quantity;
  -- anything in another unit, and anything whose delta would not parse, still
  -- comes through.
  and (
      value_delta is null
      or Unit <> 'NZD c/L'
      or abs(value_delta) >= {{ var('revision_noise_threshold_cpl') }}
  )
