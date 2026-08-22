{{ config(materialized='table') }}

{% set query %}
    select variable_name, unit_filter, canonical_name
    from {{ ref('variable_mapping') }}
    where is_fuel_specific = 'false'
{% endset %}

{% set results = dbt_utils.get_query_results_as_dict(query) %}

-- Status per variable, as in silver_fuel.
select
    Week,
    Date,
    {{ pivot_variables(results) }},
    {{ pivot_variables(results, value_column='Status', suffix='_status', cast_numeric=false) }}
from {{ source('bronze', 'weekly_prices') }}
where Fuel = 'NA'
{% set cutoff = var('simulate_cutoff_date', none) %}
{% if cutoff %}
and Date <= '{{ cutoff }}'
{% endif %}
group by Week, Date
