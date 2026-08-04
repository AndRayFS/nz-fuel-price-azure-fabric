# Architecture decisions

This documents the *why* behind the design choices in this project — not
just what the pipeline does, but why it's built this way. Written for future-me
as much as for anyone else reading the code.

## Medallion layers — what each one is actually for

- **Bronze** stores the raw MBIE snapshot exactly as it arrives. Nothing is
  cleaned, nothing is renamed. Truncate + reload every run, because the
  source itself only ever offers a full-history file, not incremental
  deltas — there's nothing to merge.
- **Silver** is where all schema complexity is absorbed. This is the one
  layer that's allowed to know the source used to look different.
- **Gold** shouldn't need to know the source ever changed. It answers
  questions (lag correlations), not "what does the raw data look like."

The goal isn't eliminating change — sources evolve, always. The goal is
localizing it, so a source-side change means editing one silver model, not
chasing it through the whole project.

## Seed-driven pivot, not hardcoded CASE WHEN

`seeds/variable_mapping.csv` maps `variable_name` (+ optional `unit_filter`,
since "Dubai crude price" appears twice with different units) to a
`canonical_name`. The silver models generate their pivot from this seed at
compile time (`dbt_utils.get_query_results_as_dict`), not from a hand-written
list of `CASE WHEN` blocks.

Adding a new tracked variable is a one-line CSV addition, not a SQL edit —
this is the whole point of the seed-driven approach argued for in Part 2 of
the writeup, actually implemented rather than just proposed.

**Adapter note:** the official dbt-fabric adapter's `run_query()` fails
inside model compilation on this project (`'None' has no attribute 'table'`).
`dbt_utils.get_query_results_as_dict` — which also calls `run_query()``
internally — works fine. This is not fully understood, just empirically
confirmed; if `run_query()` breaks again on a future dbt/adapter upgrade,
try the dbt_utils wrapper before assuming the whole approach is broken.

## TRY_CAST instead of CAST, backed by tests instead of by trusting the source

Source values are parsed with `TRY_CAST(Value AS FLOAT)`, not `CAST`. A
single malformed value in 20+ years of history shouldn't fail the entire
weekly pipeline run.

The tradeoff: `TRY_CAST` fails silently, turning bad data into `NULL` instead
of raising an error. That's closed by explicit `not_null` tests on every
value column that feeds the gold layer (`dubai_crude_usd`, `dubai_crude_nzd`,
`exchange_rate`, `board_price`, `adjusted_retail_price`). If a source ever
ships something non-numeric, the *test* fails loudly — not the pipeline, and
not a silently blank chart three weeks later.

## Lag correlation — matching the original R methodology, not a shortcut

Fabric Warehouse (T-SQL) has no built-in `CORR()`. `macros/lag_correlation_series.sql`
computes Pearson's r manually from raw sums (`ΣX`, `ΣY`, `ΣXY`, `ΣX²`, `ΣY²`)
per lag, which also matches what the original R script did deliberately —
R's own `ccf()` normalizes across the whole series regardless of lag, which
gave different (wrong, for this use case) results on short windows.

Two guards, both `NULL`, not errors:
- fewer than 3 paired points at a given lag
- zero variance in either series at that lag (division by zero otherwise)

**T-SQL quirk hit here:** `WITH` (a CTE) must be the first statement in a
batch — it can't appear inside a `UNION ALL` block. The macro is written with
nested derived-table subqueries instead of CTEs for this reason.

## Dynamic max-lag cap per period

`max_lag = min(10, floor(period_weeks / 3))`, calculated per period, not a
flat constant. A short period (e.g. the 2025 tariff shock, ~13 weeks) capped
at a flat 10 was overfitting — the "best" lag kept landing on the edge of
the tested range with a correlation that was really just noise from too few
data points. Once capped at `floor(13/3) = 4`, the artificially strong
correlation (r ≈ 0.65–0.87 at lag 9) collapsed to what it actually was
(r ≈ 0.04–0.07 at lag 4) — same rule the original R script used.

## Edge-guard (`lag_resolved`)

Even with the dynamic cap, a period's best-correlated lag can still land
exactly on the tested boundary. `lag_resolved` flags this
(`is_edge_artifact`) when the best lag equals the period's max tested lag
*and* correlation was still rising going into that boundary (i.e. r at the
edge > r one lag before it) — a sign the true peak is probably outside the
tested range, not a genuine result. Flagged rows fall back to lag=0 rather
than reporting a number that's an artifact of where the search stopped.

This isn't cosmetic: for `exchange_rate` in `03_ukraine_2022` and
`04_tariff_2025`, the artifact-flagged raw correlation was weakly positive,
but the resolved (lag=0) correlation is strongly negative (~-0.8) — which
matches the expected direction (a weaker NZD should mean a higher landed
cost, once you're not comparing the wrong lag). The guard didn't just clean
up noise, it recovered the theoretically-expected sign.

## Factor and target are both dimensions, not fixed choices

`lag_correlation` tests three factors (`dubai_crude_usd`, `dubai_crude_nzd`,
`exchange_rate`) against two targets (`board_price`, `adjusted_retail_price`),
not one hardcoded pair. The reasoning for each dimension:

- **`dubai_crude_nzd`** already embeds the exchange rate (it's USD price ÷
  NZD/USD rate). Testing it alongside `dubai_crude_usd` +
  `exchange_rate` separately isn't redundant — NZD is the single number that
  reproduces the original R analysis exactly (see below), while USD +
  exchange rate tested separately is the only way to *attribute* an effect
  to oil price versus currency movement rather than just observe their
  combined impact.
- **`board_price`** (the retailer's posted price) decomposes cleanly via
  MBIE's own identity (`Board price = Importer cost + Taxes + GST + ETS +
  Importer margin`), making it the cleaner variable for understanding the
  cost pass-through *mechanism*. **`adjusted_retail_price`** (what people
  actually pay, net of loyalty/discount schemes) is the more honest variable
  for "what does this mean for someone filling up," at the cost of adding
  retailer-side noise unrelated to cost pass-through. Neither is strictly
  correct — they answer different questions, so both are computed.

## Bug: target wasn't bounded by the period, factor was

`lag_correlation` originally filtered the *factor* series to the period's
date range before joining, but not the *target* series — the target
subquery only filtered on `Fuel`. At lag 0 this made no difference (the join
naturally stays inside the period). At larger lags, shifting a factor date
forward could land past the period's end date, silently joining against
target rows from the *next* period.

This wasn't caught by any test — `n` per lag stayed exactly right (34 for
every lag in the affected period), because the leak doesn't create or drop
rows, it just joins the wrong ones. It only surfaced by validating gold
output against the original R script's printed correlation tables: one
period (`05_calm_import_era`, which sits immediately before the ongoing
2026 crisis) had a correlation profile with the opposite sign and shape from
R's. R bounds both series to the period before computing anything, so it
can't leak across a boundary by construction; the SQL version had to be
fixed to bound the target subquery by the same `period_start`/`period_end`
as the factor.

**Lesson:** re-deriving a validated R script's logic in SQL needs the same
validation step it started with — line up final numbers against the
original before trusting the port, not just checking the SQL runs without
error. A silent join leak that keeps row counts exactly right is invisible
to schema tests; it's only caught by checking output values against a
trusted reference.

## Snapshot: what's tracked, what isn't, and why

`snapshots/mbie_revisions.sql` tracks Provisional → Final revisions via
`check` strategy on `Value` and `Status`, joined against
`variable_mapping` and filtered to `track_revisions = 'true'`.

`Importer margin trend` is excluded. It's LOESS-smoothed, which means adding
one new week's data point re-fits the *entire* historical curve — a diff
between two weekly snapshots showed ~7,000 changed rows, ~99% of them this
one column, spanning back to 2004. That's smoothing noise, not a real
revision, and including it would bury genuine revisions under thousands of
cosmetic ones every week.

**Join gotcha hit here:** the snapshot's join to `variable_mapping` originally
matched on `variable_name` alone. Since "Dubai crude price" has two rows in
the seed (USD and NZD units), every crude-price bronze row matched *both*
seed rows and got duplicated in the snapshot. Fixed by also joining on
`unit_filter`. Worth remembering for any future variable that shares a name
across units.

**One-off backfill:** a manually-saved copy of the 17 July bronze file was
merged into the snapshot after its first run, so the snapshot's history
starts from 17 July rather than from whenever `dbt snapshot` first happened
to run. Changed rows got an explicit historical version; unchanged rows had
their `dbt_valid_from` pulled back to 17 July rather than left at the
snapshot's first-run date — otherwise an as-of-17-July query would return
only the handful of rows that changed, not a full point-in-time snapshot.
This was a one-time manual fix, not a repeatable pattern — there's no
general backfill mechanism here.

## Why dbt at all, given it's a single source right now

Could have used Data Factory Script Activity directly against the Warehouse.
Chosen dbt instead because the project is explicitly meant to grow past one
source: version-controlled transformations, lineage that's generated (not
hand-maintained and therefore never stale), tests that fail before a
dashboard quietly goes wrong, and `ref()`-based environment independence.
None of that pays for itself on day one with a single source — it pays off
the day a second one shows up.

## "Is a crisis still happening?" — why this became a continuous indicator, not a yes/no flag

Report 1 (the "should I fill up now" dashboard) needs to know whether the
historical crisis-lag pattern still applies *today*. The 6 periods in
`seeds/periods.csv` were labeled by eye — start dates are reliable (each one
is pinned to a specific news event: invasion, tariffs, etc.), but end dates
were a judgment call based on looking at the oil price chart. That's fine
for retrospective analysis, but it can't be automated for a live, daily
report — there's no future data to eyeball yet.

**First idea — a volatility threshold, checked**, not assumed. Computed
rolling `STDEV` of `dubai_crude_nzd` week-over-week % change over a moving
window, compared against a calm-period baseline (`stdev` over the full
`02_calm_own_refinery` and `05_calm_import_era` periods: 0.0302 and 0.0268
respectively — so a real baseline of roughly 0.027–0.030, not a guessed
number).

**Tested against all 3 closed crisis periods (COVID, Ukraine, tariff
shock)** before trusting it. Two things fell out of that:
- Short windows (4 weeks) react fast to the *start* of a shock but are
  noisy — they can dip back near calm-baseline for a week or two in the
  *middle* of an ongoing crisis (seen clearly in the Ukraine period,
  mid-May 2022), which would cause Report 1 to falsely signal "crisis over."
- Long windows (8–10 weeks) are stable but structurally *lag* the real end
  of a crisis by nearly the window's own length, because they keep
  "remembering" old high-volatility weeks long after the raw weekly changes
  have actually calmed down.

**Tried a binary rule instead** — "3 consecutive weeks with `|pct_change| <
0.03`" — tested against the same 3 periods. It didn't fire reliably: it
never fired at all within ~6 weeks of the labeled end of COVID, and fired
2.5 weeks late for Ukraine and *almost 2 months* late for the tariff shock.
Looking at the raw weekly changes around each labeled end date explains why:
volatility doesn't switch off, it decays with occasional relapses — a rule
requiring a clean run of calm weeks will always find a later, stricter
"end" than what a human sees as a declining trend.

**Decision: no binary trigger.** Report 1 shows a continuous measure
(`% above calm baseline`) plus a trend direction (easing / intensifying),
rather than pretending there's a precise date on which a crisis regime
switches off. This is consistent with the rest of the project's stance on
honest uncertainty (edge-guard, the forecast confidence tiers) — a fabricated
yes/no answer here would be less honest than the data supports, not more
useful.

**Known limitation, deliberately out of scope for now:** this whole problem
— objectively dating regime start/end from a time series — is a real,
established field (Markov regime-switching models, going back to Hamilton
1989; the simpler Bry-Boschan peak/trough algorithm used by NBER for
recession dating). A Markov-switching model has even been applied
specifically to currency crisis prediction (Abiad, IMF 2007), which matters
here since exchange-rate "crisis periods" won't line up with oil-price ones
if that factor is ever analyzed with the same rigor. Worth revisiting with
a proper model in R/Python rather than hand-rolled SQL heuristics if this
project's forecasting ambitions grow — the rolling-volatility approach above
is a pragmatic bridge, not a claim to have solved regime detection.

## `volatility_config`: one source of truth for window size and calm baseline

Originally `factor_volatility` computed and duplicated `calm_baseline` on
every row, and the window size (`rows between N preceding`) was a Jinja
literal baked into that one model. Split into a separate one-row model,
`volatility_config` (`window_weeks`, `window_days`, `calm_baseline`), read
by both dbt (`factor_volatility`) and Power BI (DAX measures) via
`ref()`/`MAX()` respectively. Changing `volatility_window_weeks` in one
place (a dbt var) now propagates everywhere after `dbt run` + Power BI
refresh — no hunting for a hardcoded `21` or `0.0285` in a DAX formula.

That gap was found the hard way: the first version of the `Volatility
Trend` DAX measure had `21` (3 weeks) hardcoded twice, independent of the
6-week window actually configured. Doubling the window later wouldn't have
changed the trend comparison at all without a second, easy-to-forget manual
edit.

## Slope, not just r — and the forecast's honest limits

`lag_correlation_series` also returns `slope` (`(nΣXY − ΣXΣY) / (nΣX² −
(ΣX)²)`, the same regression-line slope, reusing sums already computed for
r), carried through `lag_resolved` as `resolved_slope` (falling back to the
lag-0 value under the same edge-guard logic as `resolved_r`). `r` says how
tightly two series move together; `slope` says by how much — cents per
litre per NZD/barrel of crude. Both are needed: a forecast can't be built
from correlation strength alone.

**Forecast formula:** `forecast = current_price + resolved_slope × (crude_now
− crude_lag_weeks_ago)`, using the raw NZD-denominated crude price and each
fuel's own `resolved_lag` — not a fixed window borrowed from the volatility
indicator (an early draft mistakenly used `volatility_config[window_days]`
here; the two windows serve unrelated purposes and shouldn't share a
number).

**Confidence tiers**, from `resolved_r` (not arbitrary — Cohen's *r* ≈ 0.5
is a widely-cited "large effect" threshold; several other frameworks put it
at "moderate," not "strong," so the stricter 3-tier split was chosen
deliberately over a single cutoff): `|r| ≥ 0.7` → Strong, `0.5–0.7` →
Moderate, `< 0.5` → forecast withheld entirely rather than shown with a
caveat. Showing a number with a disclaimer is easy to skim past; not
showing one at all is the honest version of "we don't know."

**Known edge case: `resolved_lag = 0`.** The forecast formula is
structurally meaningless here — "change in crude over the last 0 weeks" is
0 by construction, so the whole forecast collapses to 0% regardless of
actual conditions. `lag = 0` is a real, valid finding (same-week
pass-through), just not one this particular forward-looking formula can
use. `Forecast Display` needs to special-case it explicitly rather than
silently reporting a meaningless 0%.

## DAX filter-context bugs — same underlying cause, three symptoms

Three measures broke the same way while building the forecast, worth
recording as one lesson rather than three unrelated fixes:

1. `Volatility Trend`'s comparison window was hardcoded to 21 days instead
   of reading `volatility_config[window_days] / 2` (see above).
2. `Forecast Pct Change`/`Forecast Confidence` were reading
   `SELECTEDVALUE(lag_resolved[factor/target/fuel])` — but the Factor/
   Target/Fuel slicers are built on `lag_correlation`'s columns, not
   `lag_resolved`'s (the two tables aren't directly related to each other).
   `SELECTEDVALUE` against an unfiltered column just returns `BLANK()`,
   which silently propagated into "no forecast" for every selection.
3. After fixing (2), the forecast still changed when switching the
   *Period* slicer, even though the intent was "always show the live,
   open period's forecast regardless of what's selected." The `periods`
   table has an active relationship to `lag_resolved` (1-to-many on
   `period_id`); an explicit `CALCULATE(..., lag_resolved[period_id] =
   CurrentPeriodId)` filter does *not* override a filter arriving through
   that relationship from a different table — the two compete for the same
   column, and DAX resolves that as "no rows," not "explicit filter wins."
   Fixed by adding `ALL(lag_resolved)` as the first argument to strip every
   ambient filter (including relationship-propagated ones) before applying
   the intended explicit filters.

The general pattern worth remembering: an explicit `CALCULATE` filter on a
column doesn't automatically beat a filter that arrived at that same
column via an active relationship from a filtered table elsewhere on the
page. When a measure is meant to deliberately ignore what's selected
elsewhere on the report, `ALL()` the target table first, then apply the
intended filters — don't assume the explicit filter alone wins.

Also needed: determining "the current open period" via
`ISBLANK(periods[end_date])` reliably returned blank, for reasons not
fully diagnosed (a stray blank row that Power BI auto-adds to the "one"
side of a one-to-many relationship — visible as an extra 7th row when
`COUNTROWS(ALL(periods))` was checked against the known 6 — was the
leading suspect, but not conclusively confirmed). Replaced with
`start_date = MAX(start_date)` instead, which sidesteps the issue and is
arguably clearer intent anyway ("the most recently started period") than
relying on a null end date.

## Backtesting the forecast: does it actually predict anything, or just fit history?

Everything above validates the pipeline internally (tests pass, numbers
match R). None of it proves the forecast formula has real predictive
power — a strong historical `r` says two series moved together in the
past, not that the regression slope will hold going forward.

**Method:** a dbt var, `simulate_cutoff_date`, filters both silver models
to `Date <= cutoff` when set (`none` by default — normal runs are
untouched). Setting it and running `--full-refresh` down through
`lag_resolved` recomputes `resolved_lag`/`resolved_r`/`resolved_slope`
using only data that would genuinely have been available on that pretend
"today" — not the full-history values with hindsight baked in. The
forecast is then computed by hand against that state, and checked against
the real, already-known outcome `resolved_lag` weeks later. Data past the
cutoff isn't deleted anywhere permanent — silver/gold are fully
regenerated by a plain `dbt run --full-refresh` with no var set afterward.

**Six tests, two crisis periods (06_iranus_2026, 04_tariff_2025), mixing
rising and falling crude, short and long lookback windows:**

| # | Cutoff | Period | Lag | Error | Direction |
|---|---|---|---|---|---|
| 1 | 2026-05-22 | 06 | Diesel 3, Petrol 2 | Diesel 4.6%, Petrol ~1.7% | correct |
| 2 | 2026-06-19 | 06 | Diesel 3, Petrol 2 | Diesel 7.3%, Petrol ~1.9% | correct |
| 3 | 2026-04-10 | 06 | r weak (0.36–0.50) | forecast withheld — confidence gate worked as intended | — |
| 4 | 2026-07-03 | 06 | all = 2 | 0.4–0.9% | correct |
| 5 | 2025-05-07 | 04 | all = 0 | lag=0 edge case, formula not applicable | — |
| 6 | 2025-06-13 | 04 | Diesel 0, Petrol 1 | Petrol 0.4% | correct |

**Direction was correct in all 4 tests where a forecast was actually
produced.** Test 3 mattered as much as the successful ones: it confirmed
the confidence gate does what it's supposed to — withhold a number rather
than report a weak one dressed up as certain.

**Error scales with lag length, consistently.** Every lag-2 or lag-1
forecast landed within 2% of the real outcome; every lag-3 forecast missed
by 4.6–7.3%. Diesel happened to draw lag=3 in tests 1–2 and lag=2 in test
4 — and its own error dropped from the 4–7% range down to 0.9% exactly
when its lag did. This isn't "Diesel is a worse fuel to forecast," it's
"longer lag windows accumulate more unrelated noise between the
measurement and the outcome" — checked directly against test 4's raw
crude series, which showed a genuinely choppy, non-monotonic path (170 →
183 → 166 → 173 → 179 over the relevant weeks) rather than a clean trend,
explaining why a 3-week point-to-point comparison is noisier than a
2-week one over the same stretch.

**Practical implication, not yet implemented:** `Forecast Confidence`
currently grades purely on `resolved_r`. Given the above, a fuel with a
long resolved_lag deserves a lower confidence tier than its raw `r` alone
would suggest — e.g. downgrade one tier when `resolved_lag >= 3`,
independent of how strong the correlation looks. Worth doing before
treating Report 1's forecast as production-ready.

**Also worth noting as a real limitation, not just a caveat:** the
point-to-point comparison (`crude_now − crude_lag_weeks_ago`) is sensitive
to exactly which two weeks get compared. A choppy, non-trending market can
flip the sign of the *inferred* crude movement depending on whether the
lookback start happens to land on a local peak or trough — seen directly
in test 4, where Diesel's 3-week window and Petrol's 2-week window,
covering nearly the same stretch, inferred crude moving in *opposite*
directions from the same underlying data. A smoothed comparison (e.g.
average of the last 2 weeks vs. the 2 weeks before that, the same fix
already applied to `Volatility Trend`) would likely be more robust than
comparing two single points, but hasn't been implemented or tested.
