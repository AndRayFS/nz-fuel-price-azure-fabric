{#
  Custom schemas are used verbatim, not prefixed with the target schema.

  dbt's default would put a model configured `schema='monitoring'` into
  `dbo_monitoring`, because the built-in macro concatenates. The monitoring
  contour is meant to be a visibly separate schema — a signal store that is
  nobody's source — so `monitoring` is what it is called in the warehouse.

  Models with no `schema` config are untouched and stay in `target.schema`
  (`dbo`), which is every silver, gold and snapshot object today.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
