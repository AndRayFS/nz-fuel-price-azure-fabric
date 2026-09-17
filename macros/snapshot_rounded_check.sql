{#
  A snapshot strategy that compares `Value` as a number rounded to 4 decimals,
  and `Status` as it stands.

  Why a strategy and not a rounded column. MBIE flips the printed precision of
  `Value` between publications — it cut to ~10 significant digits on 3 Sep
  2026, restored full precision on 10 Sep, and cut again on 16 Sep. The built-in
  `check` strategy compares the stored string with the incoming one, so
  `107.498412698413` and `107.4984127` are a revision: three flips wrote 15,848
  `final_rewritten` versions each, the class that is supposed to mean history
  moved under a published report.

  Rounding the column on the way in would fix the comparison and cost two
  things: the archive would hold rounded values from then on, and the first run
  after the change would rewrite all 30,666 rows whose stored rendering differs
  from the new one — one wave of exactly the noise being removed. Overriding
  `row_changed` costs neither. The stored `Value` stays verbatim, both sides of
  the comparison are rounded, and no run writes a version for a precision flip,
  including the first.

  4 decimals, measured against both precisions as they sit in the table
  (17 Sep 2026). Of the 16,034 versions the 16 Sep load wrote, this leaves 8:
  the six genuine importer cost/margin corrections to week 2026-09-04, and two
  values within 5e-8 of a rounding boundary. A 1e-6 grid would leave 388 —
  noise of 5e-8 on values in the hundreds puts about a tenth of them near a
  boundary, and those would flip back and forth indefinitely. What 1e-4 gives
  up: revisions smaller than 1e-4 c/L stop being recorded. The real
  finalisation of 26 Aug 2026 carried 39 of those out of 773 versions, all at
  2e-5 c/L — MBIE recomputing its own arithmetic, not a price that moved.

  Everything but `row_changed` is the built-in check strategy verbatim
  (dbt-core 1.12, `macros/materializations/snapshots/strategies.sql`), so
  `check_cols` is deliberately absent from the snapshot's config: the columns
  compared are named here instead. Note the warehouse collation is
  `Latin1_General_100_BIN2_UTF8`, which makes identifiers case-sensitive —
  `Value` and `Status` are spelled as the snapshot spells them.
#}
{% macro snapshot_rounded_check_strategy(node, snapshotted_rel, current_rel, model_config, target_exists) %}
    {% set primary_key = config.get('unique_key') %}
    {% set hard_deletes = adapter.get_hard_deletes_behavior(config) %}
    {% set invalidate_hard_deletes = hard_deletes == 'invalidate' %}
    {% set updated_at = config.get('updated_at') or snapshot_get_time() %}

    {%- set old_value = 'round(try_cast(' ~ snapshotted_rel ~ '.Value as float), 4)' -%}
    {%- set new_value = 'round(try_cast(' ~ current_rel ~ '.Value as float), 4)' -%}

    {%- set row_changed_expr -%}
    (
        {{ old_value }} != {{ new_value }}
        or (({{ old_value }} is null) and not ({{ new_value }} is null))
        or ((not {{ old_value }} is null) and ({{ new_value }} is null))
        or {{ snapshotted_rel }}.Status != {{ current_rel }}.Status
        or (({{ snapshotted_rel }}.Status is null) and not ({{ current_rel }}.Status is null))
        or ((not {{ snapshotted_rel }}.Status is null) and ({{ current_rel }}.Status is null))
    )
    {%- endset %}

    {% set scd_args = api.Relation.scd_args(primary_key, updated_at) %}
    {% set scd_id_expr = snapshot_hash_arguments(scd_args) %}

    {% do return({
        "unique_key": primary_key,
        "updated_at": updated_at,
        "row_changed": row_changed_expr,
        "scd_id": scd_id_expr,
        "invalidate_hard_deletes": invalidate_hard_deletes,
        "hard_deletes": hard_deletes
    }) %}
{% endmacro %}
