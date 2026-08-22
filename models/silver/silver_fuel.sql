{{ config(materialized='table') }}

{% set query %}
    select variable_name, unit_filter, canonical_name
    from {{ ref('variable_mapping') }}
    where is_fuel_specific = 'true'
{% endset %}

{% set results = dbt_utils.get_query_results_as_dict(query) %}

-- Status is carried per variable, the same way values are. MBIE records it
-- per value, and silver reshapes rather than decides, so no week-level
-- status is invented here: whoever needs a training filter states which
-- columns it depends on.
select
    Week,
    Date,
    Fuel,
    {{ pivot_variables(results) }},
    {{ pivot_variables(results, value_column='Status', suffix='_status', cast_numeric=false) }}
from {{ source('bronze', 'weekly_prices') }}
where Fuel != 'NA'
{% set cutoff = var('simulate_cutoff_date', none) %}
{% if cutoff %}
and Date <= '{{ cutoff }}'
{% endif %}
group by Week, Date, Fuel
