# MBIE Weekly Fuel Price Data — Source Notes

Working notes on the MBIE dataset, gathered while planning the bronze/silver/gold
rebuild. These capture things that aren't obvious from just opening the CSV,
and that the pipeline/dbt design needs to account for.

## Direct download

```
https://www.mbie.govt.nz/assets/Data-Files/Energy/Weekly-fuel-price-monitoring/weekly-table.csv
```

- Always returns the **full history** (2004–present) as a single file — not
  incremental, not paginated. Safe for automated pulls (HTTP/Web activity),
  but bronze should be a full truncate+reload, not a merge.
- Stable URL, confirmed working for scheduled/unattended fetches.

## File structure — long/narrow format

Columns: `Week | Date | Variable | Fuel | Value | Unit | Status`

This is **not** a wide table — one row per (week, variable, fuel) combination.
Requires a pivot on the bronze→silver boundary, not a direct 1:1 column mapping.

**Gotcha:** the `Fuel` field uses the literal string `"NA"` for
variables that aren't fuel-specific — not a true null. Filter/parse
accordingly (`WHERE Fuel != 'NA'`, not `IS NULL`).

## Variables

**Not fuel-specific (`Fuel = "NA"`):**
- `Dubai crude price` — both USD/bbl and NZD/bbl, source: Argus Media
- `Exchange rate` — weekly average USD/NZD, source: RBNZ

**Gotcha:** the two `Dubai crude price` rows share the exact same
`Variable` text — they're only distinguished by `Unit` (`USD/bbl` vs
`NZD/bbl`). Any join or dedup logic keyed on `Variable` alone (even
combined with `Week`/`Fuel`) will silently match both and duplicate rows.
`Unit` has to be part of the key. This bit the snapshot join in practice —
see `docs/architecture.md`.

**Per fuel type** (Regular Petrol / Premium 95R / Diesel):
- `Importer cost`
- `ETS`
- `GST`
- `Taxes`
- `Price excluding tax`
- `Board price`
- `Adjusted retail price`
- `Importer margin`
- `Importer margin trend` (LOESS-smoothed)

**Decomposition identity** (useful for gold-layer sanity checks):
```
Board price = Importer cost + Taxes + GST + ETS + Importer margin
```

**Note:** there is no separate "retail margin" variable in this dataset —
confirmed against both the data dictionary and the actual CSV. Don't assume
it exists; it would have to be derived, if needed at all.

## Status field — Provisional / Final

Revisions are tied to the **quarterly** Stats NZ CPI release, not to a fixed
number of weeks. A value stays `Provisional` until the relevant quarterly CPI
data comes out and the adjustment factor is recalculated — so the gap between
Provisional and Final can be up to several months, not a short, predictable window.

**Update (confirmed by diff, 30 Jul 2026):** the quarterly cycle governs the
*Provisional → Final* transition, but Provisional values themselves can still
shift **week to week** before that transition happens. Comparing a snapshot
from 17 Jul against the file after the 24 Jul update showed real revisions to
`Importer cost`, `Importer margin`, `Dubai crude price` for the most recent
weeks — small movements, but real, not just new rows appended. Don't treat
Provisional as "stable until the quarter ends" — it's provisional in both
senses: subject to quarterly re-basing *and* to ordinary week-to-week
correction.

## `Importer margin trend` — excluded from revision tracking

A full diff between two snapshots (17 Jul vs 24 Jul) returned **7,010** changed
rows. The overwhelming majority — **6,969** — were `Importer margin trend`,
spanning the *entire* history back to 2004-04-23, including rows marked
`Final`.

This is almost certainly a LOESS-smoothing artifact, not a genuine revision.
LOESS refits the whole curve when a new point is added, so every historical
point shifts by a tiny amount — even ones long since "finalized." The `Status`
field appears to apply to the raw metrics (cost, margin, board price, etc.),
not to this derived, globally-recomputed column.

**Decision: exclude `Importer margin trend` from any snapshot/revision
tracking.** Including it would generate a near-total-history "revision" every
single week — noise, not signal, and it would defeat the purpose of tracking
revisions at all (real revisions would be buried under ~7,000 cosmetic ones).
If the trend line itself is ever needed, recompute it locally in gold from the
raw `Importer margin` values rather than trusting MBIE's version to stay
stable — since evidently it never fully does.

Everything else in the diff was small and expected: single-digit row counts,
all within the most recent 1–2 weeks, all still `Provisional` — ordinary
week-to-week correction, not a data quality problem.

## Known structural changes

- **7 May 2025** — MBIE switched to the current long/narrow format. The old
  (wide) series was discontinued 6 Aug 2025.
- **January 2026** — population weightings used in the national average were
  revised retroactively. `Price excluding tax`, `GST`, `Board price`,
  `Adjusted retail price`, `Importer margin`, and `Importer margin trend`
  were all recalculated for the window July 2025 – January 2026.
- **18 Mar 2026 – 1 Jul 2026** — MBIE paused live publication of the
  `Importer cost` and `Importer margin` series, citing volatility from the
  Middle East crisis ("to better understand these movements"). Publication
  resumed 1 July; MBIE's own explanation is on their *"Weekly fuels importer
  cost and margin restart analysis"* page.
  - **Important:** in the current downloadable file, this period shows **no
    visible gap** — all weeks are present, all marked `Provisional`. This
    strongly suggests the paused weeks were reconstructed retroactively
    after publication resumed, rather than published live.
  - Implication: these ~15 weeks are provisional in a different sense than
    the normal quarterly cycle — they may carry more uncertainty than
    ordinary Provisional data, since they weren't computed in real time.
    Worth flagging specifically when checking these rows against the
    eventual Final revision.

## Related page — fuel stock & shipping (not yet integrated)

```
https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/
energy-generation-and-markets/liquid-fuel-market/fuel-supply-disruption-response/
fuel-stock-and-shipping-updates
```

- HTML only — no downloadable file or API. Would need scraping (Data Factory
  Web activity + HTML parsing), not a Copy activity.
- **No historical archive** on the page — only a current snapshot. Updated
  weekly (was twice-weekly until 6 Jul 2026 — frequency itself has changed,
  worth recording as metadata if this is ever ingested).
- Shows days' cover (in-country / on water within EEZ / on water outside EEZ)
  for petrol, diesel, jet fuel, plus the number and names of ships in transit.
- Only useful **prospectively** — there's nothing to backfill. Good candidate
  for accumulation via a write-back table (e.g. Azure SQL), not a bronze
  source in the usual sense, since MBIE itself holds no history for it.

## Architectural implications

All of the below has since been implemented — see `docs/architecture.md`
for the actual design and the gotchas hit along the way. Kept here as the
original reasoning, for context:

- Long format requires a pivot at bronze→silver, not a direct mapping.
- Seed-driven mapping (Variable → canonical column) over hardcoded
  `CASE WHEN`, so a new Variable is a seed row, not a SQL edit.
- Adapter pattern in silver for schema evolution — MBIE has already changed
  format once (May 2025) and revised historical values retroactively
  (Jan 2026); more change should be expected, not treated as exceptional.
- Snapshot needed to track Provisional → Final revisions — the "current"
  file alone can't reveal this history, as the March–July gap
  reconstruction shows.
- `Importer margin trend` excluded from revision tracking (see above).
- Migration boundaries (format change, reweighting date, pause window)
  belong in dbt vars/seeds, not hardcoded inline across models.
