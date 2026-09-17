{% snapshot mbie_revisions %}

{{
    config(
      target_schema='dbo',
      unique_key="Week + '|' + Fuel + '|' + Variable + '|' + Unit",
      strategy='rounded_check'
    )
}}

{#- `rounded_check` rather than `check`: MBIE flips the printed precision of
    `Value` between publications, and the built-in strategy compares the stored
    string with the incoming one, so a flip reads as a revision of every
    tracked row — 15,848 `final_rewritten` versions, three weeks running, at
    deltas no larger than 5e-8 c/L. The strategy compares `Value` as a number
    rounded to 4 decimals instead. `Value` itself is still stored exactly as
    MBIE printed it, and `check_cols` is absent because the strategy names the
    columns it compares. Reasoning and the measurements behind the 4:
    `macros/snapshot_rounded_check.sql`. -#}

{#- Date is normalised here as well as in `weekly_prices_relation`, because this
    reads bronze directly and must: the snapshot IS the version record, so it
    cannot go through a macro whose other branch reads the snapshot. Rows
    already stored carry ISO strings; without this, versions written from
    3 Sep 2026 on would carry MBIE's new DD/MM/YYYY and the table would hold
    both. Date is neither in the unique key nor compared, so the format change
    itself creates no spurious revisions. -#}
select distinct
    w.Week,
    {{ mbie_date('w.Date') }} as Date,
    w.Variable,
    w.Fuel,
    w.Value,
    w.Unit,
    w.Status
from {{ source('bronze', 'weekly_prices') }} w
inner join {{ ref('variable_mapping') }} vm
    on w.Variable = vm.variable_name
    and (vm.unit_filter = w.Unit or vm.unit_filter is null)
where vm.track_revisions = 'true'

{% endsnapshot %}
