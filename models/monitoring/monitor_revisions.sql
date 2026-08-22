-- One row per revision event: a tracked value that came back different from
-- the version already held. The snapshot's `check` strategy on
-- (`Value`, `Status`) means a second version exists only when one of them
-- actually moved, so every row below is a real change, not a re-run.
--
-- This is a signal, not an input. Nothing in silver or gold reads it, and it
-- cannot stop a run — the run's only stopping point is the freshness gate.
--
-- `Importer margin trend` is absent by construction: it is excluded from the
-- snapshot itself as LOESS re-fit noise (architecture.md).

with versioned as (

    select
        Week,
        Date,
        Fuel,
        Variable,
        Unit,
        Value,
        Status,
        cast(dbt_valid_from as date)                            as detected_on,
        row_number() over (
            partition by Week, Fuel, Variable, Unit
            order by dbt_valid_from)                            as version_no,
        lag(Value) over (
            partition by Week, Fuel, Variable, Unit
            order by dbt_valid_from)                            as prior_value,
        lag(Status) over (
            partition by Week, Fuel, Variable, Unit
            order by dbt_valid_from)                            as prior_status
    from {{ ref('mbie_revisions') }}

)

select
    detected_on,
    Week,
    Date,
    Fuel,
    Variable,
    Unit,
    prior_status,
    Status                                                      as new_status,
    TRY_CAST(prior_value as float)                              as prior_value,
    TRY_CAST(Value as float)                                    as new_value,
    TRY_CAST(Value as float) - TRY_CAST(prior_value as float)   as value_delta,
    -- `final_rewritten` is the one that matters: a week MBIE had already
    -- called Final came back with a different number, which silently moves
    -- history under a report whose subject is what the model got wrong.
    -- `finalised_unchanged` is the routine weekly transition and carries no
    -- information beyond the date it happened.
    case
        when prior_status = 'Provisional' and Status = 'Final'
             and TRY_CAST(Value as float) = TRY_CAST(prior_value as float)
            then 'finalised_unchanged'
        when prior_status = 'Provisional' and Status = 'Final'
            then 'finalised_revised'
        when prior_status = 'Final' and Status = 'Final'
            then 'final_rewritten'
        when prior_status = 'Provisional' and Status = 'Provisional'
            then 'provisional_revised'
        else 'other'
    end                                                         as revision_class
from versioned
where version_no > 1
