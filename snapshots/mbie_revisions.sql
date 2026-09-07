{% snapshot mbie_revisions %}

{{
    config(
      target_schema='dbo',
      unique_key="Week + '|' + Fuel + '|' + Variable + '|' + Unit",
      strategy='check',
      check_cols=['Value', 'Status']
    )
}}

{#- Date is normalised here as well as in `weekly_prices_relation`, because this
    reads bronze directly and must: the snapshot IS the version record, so it
    cannot go through a macro whose other branch reads the snapshot. Rows
    already stored carry ISO strings; without this, versions written from
    3 Sep 2026 on would carry MBIE's new DD/MM/YYYY and the table would hold
    both. Date is neither in the unique key nor in check_cols, so the format
    change itself creates no spurious revisions. -#}
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
