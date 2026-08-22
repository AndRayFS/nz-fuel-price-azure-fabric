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
    {#- As at the END of the named day, not its midnight. A snapshot run on the
        13th stamps dbt_valid_from at that morning's hour, so `<= '2026-08-13'`
        would compare against midnight and return the state BEFORE that day's
        run. `--as-of 13 Aug` has to mean "as the 13th left it", not "as the
        12th left it", not least because the git half of a vintage resolves the
        commit with --before='DATE 23:59:59' and the two halves must agree.
        Validity is the half-open interval [valid_from, valid_to), so at the
        instant T = start of the next day a row is visible when
        valid_from < T and (valid_to is null or valid_to >= T). -#}
    (select Week, Date, Fuel, Variable, Unit, Value, Status
     from {{ ref('mbie_revisions') }}
     where dbt_valid_from < dateadd(day, 1, cast('{{ vintage }}' as date))
       and (dbt_valid_to is null
            or dbt_valid_to >= dateadd(day, 1, cast('{{ vintage }}' as date))))
  {%- else -%}
    {{ source('bronze', 'weekly_prices') }}
  {%- endif -%}
{% endmacro %}
