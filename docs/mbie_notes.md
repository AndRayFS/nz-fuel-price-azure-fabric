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

## How `Importer cost` is actually built — and why that matters

Read from the primary source on 13 Aug 2026: MBIE's *Weekly fuel monitoring
methodology*, https://www.mbie.govt.nz/dmsdocument/30707-weekly-fuel-price-monitoring-methodology
(PDF; the HTML pages do not contain this detail). The formula:

```
Importer cost = Cost to purchase fuel + Cost to ship fuel + Wharfage
```

- **The base price is a Singapore refined-product spot quote, not crude.**
  "All prices are calculated using Singapore product spot prices," supplied
  weekly by Argus Media. Petrol → Gasoline 95 RON unleaded; diesel →
  Gasoil 50ppm (high pour).
- **Shipping** is the Worldscale flat rate (Envisory, quarterly) × the
  Singapore–Asia-Pacific route rate (Argus, weekly), plus a freight
  adjustment for the NZ leg, plus insurance and loss factors.
- **FX** is RBNZ's rate, converting USD/bbl to NZc/L.
- **Wharfage** is added last.

**There is no purchase date, no voyage time, and no averaging window
anywhere in the calculation.** It is this week's Singapore spot at this
week's exchange rate. That makes `Importer cost` a **replacement-cost
estimate** — what importing would cost right now — not what anyone paid for
the fuel currently in the tanks. Two consequences:

1. Physical procurement lag is **invisible in this dataset**, not absent
   from the world. Any claim that the crude→pump lag is a pricing decision
   rather than shipping time cannot be made from this file — see the
   correction in `architecture.md`.
2. Dubai crude is one step upstream of what actually drives the series.
   The right factor, if one is ever added, is the Argus Singapore product
   quote (Gasoline 95 RON, Gasoil 50ppm), not another crude benchmark.

**Weekly vs quarterly inputs.** Only two inputs move weekly — the Singapore
spot price and the exchange rate (route rate also weekly). The quality
premium, octane adjustment, Worldscale flat rate, freight adjustment,
insurance rate, loss rate, bbl/t conversion and wharfage are all
**quarterly**. So week-to-week movement in `Importer cost` is essentially
spot × FX, which is why it correlates with crude at lag 0 with a sharp
peak.

For correlation and slope work this matters less than it first appears: a
stale quarterly constant shifts the whole series by an offset, and an
additive offset changes neither `r` nor the slope. It matters for anything
read as a *level*.

## Trustworthiness is not uniform across columns

Ranked by distance from direct observation. This distinction was implicit
until 13 Aug 2026 and the project had been treating all columns as equally
observational.

| Column | Kind | Notes |
|---|---|---|
| `Board price` | Observation | Actual pump prices, Datamine, daily since 2022. The most solid series in the file. |
| `Dubai crude`, `exchange rate` | Market quotes | External, verifiable. |
| `Adjusted retail price` | Observation + quarterly correction | Carries the quarterly adjustment factor (see below). |
| `Importer cost` | **Model** | Weekly movement is real (spot × FX); level depends on quarterly constants. |
| `Importer margin` | **Residual of a residual** | `Adjusted retail − Taxes and levies − Importer cost`. Every error in the cost model lands here with the sign flipped. |
| `Importer margin trend` | LOESS-smoothed | Presentation only. Already excluded from revision tracking. |

**The project's headline result — the lag between crude and pump price —
uses only rows from the top two tiers, so it is unaffected by any of this.**
What is affected is the margin work: `Importer margin` is the weakest
column in the file *and* the one the roadmap wants to analyse. Any finding
there needs an explicit check that it is not an artifact of MBIE's cost
model before it can be read as retailer behaviour.

MBIE is not overselling any of this — the series exists for market
transparency ("does the margin look reasonable?"), not as a research
dataset. The mismatch is on the consuming end.

## Board price vs Adjusted retail price — the adjustment factor is quarterly, not weekly

`Adjusted retail price = Board price − adjustment factor`. Per MBIE's own
methodology document, the factor is computed **once per quarter** — by
comparing MBIE's quarterly average price against Stats NZ's CPI fuel price
for that same quarter — and then applied unchanged to every week within
that quarter.

**Confirmed empirically (2 Aug 2026):** for the ongoing 2026 Iran/US
conflict period, the gap between `board_price` and `adjusted_retail_price`
on bronze is a constant **2.898360974938** c/L across every week observed so
far (Regular Petrol, Mar–Jul 2026), matching to 12 decimal places. This
isn't a pipeline artifact — it's the quarterly factor genuinely not having
been recalculated yet for this Provisional period.

**Why this matters for lag correlation:** Pearson's r is invariant to an
additive constant — `r(X, Y) = r(X, Y + c)`. Since the two target columns
differ only by a constant within any given quarter, `lag_correlation` and
`lag_resolved` produce **mathematically identical** results for
`board_price` vs `adjusted_retail_price` whenever a period's data hasn't
crossed a quarter boundary with a factor update yet. This is expected to
resolve itself once the current quarter's CPI comes out and the factor is
recalculated — at which point the two targets should start diverging for
this period the way they already do for the closed historical ones.

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

- **1 Jan 2022 — the retail price source changed, and it is visible in the
  data.** Per the methodology document's data-source table, retail fuel
  prices come from **Envisory up to 31 Dec 2021** and from **Datamine from
  1 Jan 2022**. This was not recorded here until 13 Aug 2026, and it turned
  out to be load-bearing — see the rolling-window analysis in
  `architecture.md`. Two fingerprints, both sharp at the boundary:
  - **Repeated weekly values stop dead.** Weeks where `Board price` is
    unchanged from the previous week were routine — 5 to 23 per year per
    fuel through 2021 — and the last one is **24 Dec 2021**, for both
    petrol and diesel. From the first week of 2022 to the present, across
    ~230 weeks, there is not a single one.
  - **Diesel's precision changes.** Before 2022, 15–31 of ~52 diesel values
    a year were finer than 0.1 c/L; from 2022, all 52 are. Petrol had
    already been at full precision since 2019, so **the series change is
    larger for diesel than for petrol**.
  - **Why this matters:** it lands 13 weeks before Marsden Point stopped
    refining (31 Mar 2022), so any before/after comparison across that
    boundary is confounded — and confounded *asymmetrically by fuel*,
    which is exactly the shape of the effect it would be mistaken for.
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
