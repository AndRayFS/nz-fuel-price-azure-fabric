{% snapshot mbie_revisions %}

{{
    config(
      target_schema='dbo',
      unique_key="Week + '|' + Fuel + '|' + Variable + '|' + Unit",
      strategy='check',
      check_cols=['Value', 'Status']
    )
}}

select distinct
    w.Week,
    w.Date,
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
