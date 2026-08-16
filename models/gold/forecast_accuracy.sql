-- Report 1's time axis: what the model said, what happened, and whether it
-- was any good — every week, not just the latest one.
--
-- Source is seeds/forecast_history.csv, a WALK-FORWARD BACKTEST: every row
-- was produced refitting on data available at that week only. It is a
-- retrospective simulation, not a record of forecasts that were published
-- at the time. Any visual built on this must say so.
--
-- `skill` is the honest headline: 1 - (model error / naive error) over a
-- trailing window. Above zero means the model beat "the price won't move";
-- below zero means it did not, and the report should be willing to show
-- that rather than hide it.
--
-- Trailing 26 weeks, not expanding: readers want "is it working lately",
-- and an expanding window would let a good 2014 bury a bad 2026.

{{ config(materialized='table') }}

with base as (
    select
        week_date,
        target_week,
        fuel,
        h                                    as horizon_weeks,
        input_status,
        outcome_known,
        price_now,
        actual_price,
        pred_adl,
        pred_adl_ecm,
        pred_naive,
        pred_report1_ish,
        abs(err_adl)         as abs_err_adl,
        abs(err_adl_ecm)     as abs_err_adl_ecm,
        abs(err_naive)       as abs_err_naive,
        abs(err_report1_ish) as abs_err_report1
    from {{ ref('forecast_history') }}
),

rolled as (
    select
        *,
        avg(abs_err_adl_ecm) over (
            partition by fuel, horizon_weeks order by week_date
            rows between 25 preceding and current row) as mae_model_26w,
        avg(abs_err_naive) over (
            partition by fuel, horizon_weeks order by week_date
            rows between 25 preceding and current row) as mae_naive_26w,
        avg(abs_err_report1) over (
            partition by fuel, horizon_weeks order by week_date
            rows between 25 preceding and current row) as mae_report1_26w,
        -- count the ERRORS, not the rows: the newest rows have no outcome
        -- yet and must not make a window look full when it is not.
        count(abs_err_naive) over (
            partition by fuel, horizon_weeks order by week_date
            rows between 25 preceding and current row) as window_n
    from base
)

select
    r.*,
    -- Null until the window is full, so a partial window is never charted
    -- as if it carried the same weight.
    case when r.window_n = 26 and r.mae_naive_26w > 0
         then 1.0 - r.mae_model_26w / r.mae_naive_26w end as skill_26w,
    case when r.window_n = 26 and r.mae_naive_26w > 0
         then 1.0 - r.mae_report1_26w / r.mae_naive_26w end as skill_report1_26w
from rolled r

-- Regime context (crude_vol_regime, crude_episode_id) is deliberately NOT
-- joined here. seeds/period_flags.csv belongs to the labelling thread and
-- the decision to register and load it is still open; joining it would make
-- this model fail until that lands. Add the join once it is merged.
