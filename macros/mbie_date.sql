{#
  MBIE's `Date` column, as an ISO `YYYY-MM-DD` string.

  Bronze is a verbatim copy of `weekly-table.csv`, and on 3 Sep 2026 MBIE
  changed the format of that column across the whole file — every week back to
  2004 arrived as `28/08/2026` where it had been `2026-08-21`. Nothing in the
  project stores the column as a date: it is `varchar` in bronze, in silver and
  in the snapshot, and the code relies on ISO strings sorting and comparing as
  text (`order by Date`, `Date <= '{{ cutoff }}'`, the join to the AIP seed in
  `monitor_aip_gap`). So the fix restores the ISO *string* rather than changing
  the type — every model below the seam is then unaffected.

  The dangerous half is that 39% of the new values parse anyway: MBIE means
  6 December by `06/12/2026`, and `try_cast` under us_english returns 12 June,
  silently swapping day and month wherever the day is 12 or less. Only days
  past the 12th fail loudly.

  Both formats are accepted because the source has now demonstrated it changes
  this without notice, and bronze is truncated and reloaded whole every week —
  so a reversion would arrive the same way, in one piece, unannounced.
  `coalesce` rather than one style because style 103 does NOT parse ISO here:
  `try_convert(date, '2026-08-21', 103)` returns NULL in Fabric (checked
  3 Sep 2026). Order matters only in that 103 is tried first; the two accept
  disjoint sets of strings.

  `pipeline/fabric_io.py` carries the same expression as `MBIE_DATE` for the
  gate and the closing marker, which are Python and cannot call a macro.
  Two definitions, both in git; any new reader uses one of them rather than
  copying the SQL again.
#}
{% macro mbie_date(col) -%}
convert(varchar(10), coalesce(try_convert(date, {{ col }}, 103), try_cast({{ col }} as date)), 23)
{%- endmacro %}
