{% macro pivot_variables(mapping_rows) %}
  {% for row in mapping_rows %}
    max(case when Variable = '{{ row["variable_name"] }}'
      {%- if row["unit_filter"] %} and Unit = '{{ row["unit_filter"] }}'{% endif %}
      then Value end) as {{ row["canonical_name"] }}
    {%- if not loop.last %},{% endif %}
  {% endfor %}
{% endmacro %}
