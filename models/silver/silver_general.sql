{{ config(materialized='table') }}

{% set query %}
    select variable_name, unit_filter, canonical_name
    from {{ ref('variable_mapping') }}
    where is_fuel_specific = 'false'
{% endset %}

{% set results = dbt_utils.get_query_results_as_dict(query) %}

select
    Week,
    Date,
    {% for i in range(results['variable_name'] | length) %}
    max(case when Variable = '{{ results["variable_name"][i] }}'
        {%- if results["unit_filter"][i] %} and Unit = '{{ results["unit_filter"][i] }}'{% endif %}
        then TRY_CAST(Value AS FLOAT) end) as {{ results["canonical_name"][i] }}
    {%- if not loop.last %},{% endif %}
    {% endfor %}
from {{ source('bronze', 'weekly_prices') }}
where Fuel = 'NA'
group by Week, Date
