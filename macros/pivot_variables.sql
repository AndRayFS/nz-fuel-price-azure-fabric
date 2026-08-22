{#
  One row per grain, one column per variable, from the long bronze table.

  `mapping` is the dict-of-lists that
  `dbt_utils.get_query_results_as_dict(...)` returns over `variable_mapping`
  — keys `variable_name`, `unit_filter`, `canonical_name`, each a list, all
  the same length. That is the shape the callers already have; the macro
  does not re-query it.

  `Unit` is part of the match, not decoration: `Dubai crude price` has a USD
  row and an NZD row, and matching on `Variable` alone collides them.

  Called twice per model — once for the values, once for `Status` — so the
  case-when shape lives in one place rather than four.
#}
{% macro pivot_variables(mapping, value_column='Value', suffix='', cast_numeric=true) %}
  {%- for i in range(mapping['variable_name'] | length) %}
    max(case when Variable = '{{ mapping["variable_name"][i] }}'
        {%- if mapping["unit_filter"][i] %} and Unit = '{{ mapping["unit_filter"][i] }}'{% endif %}
        then {% if cast_numeric %}TRY_CAST({{ value_column }} AS FLOAT){% else %}{{ value_column }}{% endif %} end)
        as {{ mapping["canonical_name"][i] }}{{ suffix }}
    {%- if not loop.last %},{% endif %}
  {%- endfor %}
{% endmacro %}
