{#
  Which relation silver reads: bronze as it stands now, or the snapshot as it
  stood on a date.

  Two different questions get confused constantly, so they are named apart:

    simulate_cutoff_date  — observation date. "Weeks up to August", with
                            today's corrected values in them.
    as_of_vintage         — vintage. "What was believed in August", including
                            values MBIE has since revised.

  Setting both is refused rather than resolved. The composition has no
  interpretation: it would return weeks up to one date, valued as at another,
  and no reader could say which number came from where.

  The vintage branch reads the snapshot, not bronze, because bronze holds one
  copy of the current MBIE file and is overwritten by every ingest. The
  snapshot IS the version record. Horizon is therefore 17 July 2026, the
  backfill date — before that there is exactly one version and a vintage run
  reproduces current numbers.

  Column list is spelled out rather than `select *`: the snapshot carries
  dbt_scd_id / dbt_updated_at / dbt_valid_from / dbt_valid_to as well, and
  they must not reach the pivot.
#}
{% macro weekly_prices_relation() %}
  {%- set vintage = var('as_of_vintage', none) -%}
  {%- set cutoff  = var('simulate_cutoff_date', none) -%}

  {%- if vintage and cutoff -%}
    {{ exceptions.raise_compiler_error(
         "as_of_vintage (" ~ vintage ~ ") and simulate_cutoff_date (" ~ cutoff ~
         ") are both set. They answer different questions - vintage is what was "
         ~ "known on a date, cutoff is which weeks are visible - and together "
         ~ "they produce a mixture with no interpretation. Set one.") }}
  {%- endif -%}

  {%- if vintage -%}
    (select Week, Date, Fuel, Variable, Unit, Value, Status
     from {{ ref('mbie_revisions') }}
     where dbt_valid_from <= '{{ vintage }}'
       and (dbt_valid_to is null or dbt_valid_to > '{{ vintage }}'))
  {%- else -%}
    {{ source('bronze', 'weekly_prices') }}
  {%- endif -%}
{% endmacro %}
