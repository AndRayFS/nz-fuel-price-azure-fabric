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
treating Report 1's forecast as production-ready. **Superseded 11 Aug
2026** — grade on the lag's margin of victory instead; see the diesel
correction below and roadmap item 1.

**Test 4 reads differently after that correction.** Its cutoff
(2026-07-03) is one of the weeks where diesel's lag 2 and lag 3 fit the
data equally well (r = 0.8334 vs 0.8294, a gap of 0.004). So "diesel's
error dropped to 0.9% exactly when its lag dropped to 2" is not a lag
length effect cleanly isolated — it is two statistically indistinguishable
models producing forecasts that differ by several percent. That is a
sharper warning about point forecasts than the original reading, and an
argument for reporting a range across the top competing lags rather than
committing to the argmax. The lag-length pattern across tests 1–2, 4 and 6
still holds as an observation; the diesel-specific causal gloss on it does
not.

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

## Diesel's "lag shift" was a flat peak, not a regime change — corrected 13 Aug 2026

**This section previously reported that diesel holds lag=3 for 14 weeks,
shifts to lag=2 for exactly three weeks (3–17 Jul), then reverts, and that
the shift lines up with a fast decline in `Importer margin`. Re-measured
with the margin of victory recorded alongside the winning lag, that reading
does not survive.** The corrected version is below; the margin hypothesis
is not disproven, but it was never tested against the right quantity.

The original expanding-window query recorded only `argmax(r)` per week. It
never asked **by how much** the winning lag won. That gap is the whole
question, because `lag_resolved` already exposes exactly this quantity for
the full period (`lag_confidence_gap`) and it is tiny for diesel:

All figures in this section are from the 13 Aug 2026 refresh (MBIE data
through 2026-08-07), `dubai_crude_nzd` × `board_price`. The same numbers
hold for `adjusted_retail_price`: within a quarter the two targets differ
by a constant, and `r` is invariant to that — see `mbie_notes.md`.

| period | fuel | best lag | best r | 2nd lag | 2nd r | gap |
|---|---|---|---|---|---|---|
| 06_iranus_2026 | Diesel | 3 | 0.9000 | 2 | 0.8947 | **0.0053** |
| 06_iranus_2026 | Regular Petrol | 2 | 0.9226 | 3 | 0.8599 | 0.0627 |
| 06_iranus_2026 | Premium 95R | 2 | 0.9207 | 3 | 0.8599 | 0.0608 |
| 02_calm_own_refinery | Regular Petrol | 3 | 0.9600 | 4 | 0.9597 | 0.0003 |

**"Diesel's lag is 3, petrol's is 2" rests on a third-decimal
difference.** Petrol's own lag=2 is separated an order of magnitude better
(0.0627 against 0.0053, ~12×). Any statement that treats diesel's 3 as a
fact about diesel, rather than as a coin flip between two near-identical
fits, is overclaiming.

Re-running the expanding window with `r` at every lag retained, diesel in
`06_iranus_2026` (`dubai_crude_nzd` × `board_price`, cutoffs with n≥6):

| cutoff | n | max lag allowed | best | r@2 | r@3 | r@3 − r@2 |
|---|---|---|---|---|---|---|
| 2026-04-24 | 6 | 2 | 2 | 0.7288 | — | lag 3 not testable |
| 2026-05-01 | 7 | 2 | 2 | 0.7323 | — | lag 3 not testable |
| 2026-05-08 | 7 | 3 | 3 | 0.7461 | 0.9619 | +0.2158 |
| 2026-05-15 | 8 | 3 | 3 | 0.7523 | 0.9561 | +0.2038 |
| 2026-05-22 | 9 | 3 | 3 | 0.7681 | 0.9283 | +0.1602 |
| 2026-05-29 | 10 | 4 | 3 | 0.7769 | 0.9320 | +0.1551 |
| 2026-06-05 | 11 | 4 | 3 | 0.7766 | 0.9222 | +0.1457 |
| 2026-06-12 | 12 | 4 | 3 | 0.7926 | 0.8855 | +0.0929 |
| 2026-06-19 | 13 | 5 | 3 | 0.7989 | 0.8692 | +0.0703 |
| 2026-06-26 | 14 | 5 | 3 | 0.8013 | 0.8392 | +0.0379 |
| 2026-07-03 | 16 | 5 | **2** | 0.8334 | 0.8294 | −0.0039 |
| 2026-07-10 | 17 | 6 | **2** | 0.8599 | 0.8566 | −0.0034 |
| 2026-07-17 | 18 | 6 | **2** | 0.8793 | 0.8788 | −0.0005 |
| 2026-07-24 | 18 | 6 | 3 | 0.8901 | 0.8917 | +0.0016 |
| 2026-07-31 | 19 | 7 | 3 | 0.8951 | 0.8966 | +0.0015 |
| 2026-08-07 | 20 | 7 | 3 | 0.8947 | 0.9000 | +0.0053 |

**There is no three-week shift.** Lag 3's advantage decays monotonically —
0.216, 0.204, 0.160, 0.155, 0.146, 0.093, 0.070, 0.038 — and from 3 Jul
onward the two lags are tied to the third or fourth decimal. The "shift to
2 and back" is the argmax flipping on a tie. Reading a regime change into
it was reading structure into rounding noise.

**The first apparent transition is a different artifact: the max-lag cap.**
Under the dynamic cap (`min(10, weeks // 3)`, see above), lag 3 is not in
the search space at all until 8 May, so the 2→3 "transition" that week is
the ceiling lifting, not the data changing. This also explains the
discrepancy with the original write-up, which reported lag=3 holding from
10 Apr: that query must have used a fixed max lag for every cutoff. Both
choices are defensible — recomputing the cap per cutoff is honest about
what was knowable at the time, a fixed cap makes the weeks comparable —
but they must not be mixed, and the earlier finding mixed them. **Under
either rule the conclusion collapses:** with a fixed cap the cap artifact
disappears and only the two tied July flips remain.

**What is real, and is the actual finding here:** the convergence itself.
`r` at lag 2 rises monotonically with sample size (0.729 → 0.895) while
`r` at lag 3 falls monotonically (0.962 → 0.897). That is an eight-week
systematic drift, not week-to-week noise. Whatever explanation gets
attached to diesel — margin, asymmetric pass-through, anything else —
has to explain a smooth convergence over two months, not a three-week
excursion. **The margin correlation reported previously was matched
against a window that does not exist**; it has not been tested against
the drift and should be treated as untested rather than supported.

The asymmetric-pass-through literature ("rockets and feathers," Bacon 1991
onward; a 2026 paper finding the asymmetry stronger during crises; prior
work finding diesel's refining-stage asymmetry distinct from petrol's)
remains a plausible frame and is why the margin work stays top of the
roadmap. It is background reading, not evidence for anything measured here
yet.

## Lag stability separates crisis from calm — WITHDRAWN 15 Aug 2026

> **This finding does not survive a measured regime definition.** It was
> computed against the hand-drawn `periods.csv`, which labelled
> `04_tariff_2025` a crisis when crude actually *fell* 9.8% across it and no
> week clears any volatility threshold. Recomputed on 2010+ against
> `crude_vol_regime` (26-week window, lags 0–8, board price on crude
> levels, i.e. the original method):
>
> | fuel | regime | n | weeks the best lag changed | median gap to 2nd |
> |---|---|---|---|---|
> | petrol | normal | 724 | 14.5% | 0.0212 |
> | petrol | **high** | 109 | **17.4%** | **0.0168** |
> | diesel | normal | 724 | 12.7% | 0.0229 |
> | diesel | **high** | 109 | **18.3%** | **0.0113** |
>
> The *calm* half of the original observation reproduces — the winning lag
> does wander in quiet periods, about 12–15% of weeks. What does not
> reproduce is the contrast. High-volatility weeks are **less** stable and
> **less** decisive, for both fuels: the lag changes more often and the
> winner's margin over the runner-up is 20–50% smaller. The claimed
> separation was an artifact of the mislabelled windows.
>
> This is consistent with everything found on 15 Aug: the crisis is where
> the pass-through estimate destabilises too. The text below is kept for
> the record and should not be quoted.

## Lag stability separates crisis from calm — an unplanned finding

The same expanding-window run across *all* periods, counting how often the
winning lag changes from one cutoff to the next (n≥6, `dubai_crude_nzd` ×
`board_price`):

| period | fuel | cutoffs | distinct lags | transitions |
|---|---|---|---|---|
| 01_covid_2020 | all three | 9 | 1 | **0** |
| 02_calm_own_refinery | Diesel | 85 | 10 | **27** |
| 02_calm_own_refinery | Regular Petrol | 84 | 7 | **28** |
| 03_ukraine_2022 | Diesel | 21 | 3 | 3 |
| 04_tariff_2025 | all three | 7 | 2 | 3 |
| 05_calm_import_era | Diesel | 28 | 9 | **10** |
| 06_iranus_2026 | Diesel | 16 | 2 | 3 |
| 06_iranus_2026 | Regular / Premium | 16 | 1 | **0** |

During a shock the crude signal dominates, the peak is sharp and the
winning lag sits still. During calm the search is fitting noise: 27–28
changes over 85 weeks, up to 10 different "best" lags. This is a genuinely
independent read on `periods.csv` — the seed's crisis/calm labels were set
from news events, and an unrelated property of the data agrees with them.

Two consequences. First, a stability signal is worth building (roadmap
item 1) — but keyed on the gap, not on argmax changes, since for diesel
argmax measures a coin flip. Second, `resolved_lag` for calm periods should
carry a health warning wherever it is displayed; `02_calm_own_refinery`'s
lag=3 at r=0.96 looks authoritative and is one of 10 values the search
wandered through.

## Crude lands on `Importer cost` at lag 0 — and what that does and doesn't prove

Same lag search, same factor (`dubai_crude_nzd`), target swapped from
`board_price` to `importer_cost`, all periods and fuels (13 Aug 2026):

| period | fuel | lag → board | r board | lag → cost | r cost | gap cost |
|---|---|---|---|---|---|---|
| 01_covid_2020 | Regular Petrol | 0 | 0.8016 | 0 | 0.9108 | 0.3089 |
| 02_calm_own_refinery | Regular Petrol | 3 | 0.9600 | 0 | 0.9937 | 0.0027 |
| 02_calm_own_refinery | Diesel | 4 | 0.9624 | 0 | 0.9920 | 0.0084 |
| 03_ukraine_2022 | Regular Petrol | 0 | 0.7603 | 0 | 0.8787 | 0.1874 |
| 04_tariff_2025 | Regular Petrol | 2 | 0.8374 | 0 | 0.8903 | 0.7033 |
| 05_calm_import_era | Regular Petrol | 10 | 0.5164 | 5 | 0.5906 | 0.0020 |
| 06_iranus_2026 | Diesel | 3 | 0.9000 | 1 | 0.7876 | 0.0070 |
| 06_iranus_2026 | Regular Petrol | 2 | 0.9226 | 0 | 0.8844 | 0.0780 |

**`Importer cost` peaks at lag 0 in 15 of 18 rows, with a far sharper peak
than `board_price` ever shows** (gap 0.19–0.70 in crisis periods, against
0.003–0.07 for board price). Reading the methodology afterwards explains
why exactly: the series is this week's Singapore product spot at this
week's RBNZ exchange rate, with no purchase date and no voyage time
anywhere in it — see "How `Importer cost` is actually built" in
`mbie_notes.md`. The lag-0 result is the arithmetic of a replacement-cost
construction, not a fact about how fast the market moves.

**What this does not license.** The tempting conclusion — "cost reacts
instantly, therefore the 2–3 weeks before pump prices move is a retailer
pricing decision, not shipping time" — was drafted and then withdrawn.
Real cargoes still take weeks to arrive; MBIE's series simply does not
record when any of them were bought. So the crude→`board_price` lag is a
delay against a *notional current* cost and **cannot be decomposed into
physical procurement versus pricing behaviour with this dataset**. That
decomposition needs a source MBIE does not publish.

**A refinery-era effect was hypothesised and then ruled out.** `Importer
cost` tracks crude at r=0.99 in `02_calm_own_refinery` but only 0.45–0.59
in `05_calm_import_era`, which looked like the 2022 refinery closure
severing a direct crude link. It is a range-restriction artifact:

| period | weeks | crude range (% of mean) | crude CV | cost CV |
|---|---|---|---|---|
| 02_calm_own_refinery | 90 | 90% | 24.3% | 25.9% |
| 05_calm_import_era | 34 | 18% | 4.5% | 4.2% |
| 06_iranus_2026 | 23 | 91% | 23.8% | 12.6% |

Crude's spread is five times narrower in the import era, and correlation
falls mechanically when the signal shrinks toward the noise. The CV ratio
between cost and crude is preserved across both eras (24.3 vs 25.9, then
4.5 vs 4.2) — the relationship did not weaken, the variation did. No
structural break is demonstrated, and the hypothesis is dropped rather
than parked.

**One anomaly that survives, and it is a data-quality signal.**
`06_iranus_2026` is the only period where `importer_cost` fits crude
*worse* than retail `board_price` does (diesel 0.788 vs 0.900), and the
only period where cost varied far less than crude (CV ratio 0.53, against
0.77–1.94 everywhere else) — the series looks damped. That period is also
the one MBIE stopped publishing live and reconstructed retroactively
(18 Mar – 1 Jul 2026, `mbie_notes.md`). Suggestive, not conclusive, but it
means `importer_cost` and `importer_margin` for the current crisis should
not be treated as equivalent in quality to the rest of the history.

## Rolling window over all 22 years — the single-best-lag method is weakly identified

Everything above works inside hand-picked periods from `periods.csv`. That
seed encodes a hypothesis (these weeks are a crisis, those are calm), and
after two findings collapsed under scrutiny it was worth checking the
method itself without it. Data coverage turned out to be complete: **1164
weeks, 23 Apr 2004 to 7 Aug 2026, no nulls** in crude, exchange rate,
`board_price` or `importer_cost`.

Design: a fixed 26-week window, stepped one week at a time, lags 0–8
(which is the project's own `weeks // 3` rule evaluated once for a 26-week
window — a *constant* ceiling, so the cap artifact documented above cannot
occur here). Best lag, its `r`, and its gap over the runner-up recorded per
window; 1138 windows per fuel.

**Finding 1, as first written, was wrong — the window width was doing the
work.** The original claim was "ties are the norm: only 14–20% of windows
have a gap ≥ 0.05." That number is entirely a consequence of picking 26
weeks, which was chosen because `26 // 3 = 8` gives a constant lag ceiling
— a reason to fix the width, not a reason for that width. Re-run at three
widths (share of windows with gap ≥ 0.05):

| width | Diesel | Regular Petrol |
|---|---|---|
| 13 weeks | 46.8% | 44.4% |
| 26 weeks | 17.7% | 16.2% |
| 52 weeks | 9.1% | 5.5% |

At a width comparable to an actual crisis (13 weeks), roughly 70% of
windows have a single sharp peak. The 26-week sweep was mostly measuring
mixtures of regimes: only **two** windows of 26 weeks fit entirely inside
any crisis period, and none of 52 weeks, because crises here run 13–27
weeks. **Window width is a parameter of the analysis and has to be
reported as one.**

**Finding 2, "the typical lag over the history is 1 week", is withdrawn.**
Most windows are dominated by non-crisis weeks where, as established
above, the search is fitting noise. The modal lag of a wandering argmax is
not a market property.

**Finding 1', which does survive and is the useful one — the lag profile
is a smooth unimodal hill.** The runner-up lag is the winner's immediate
neighbour in 92–100% of windows, at every width, for both fuels. Extending
to the third and fourth places:

| width | fuel | top-2 adjacent | top-3 contiguous | top-4 contiguous | mean distance 1→3 | 1→4 |
|---|---|---|---|---|---|---|
| 13 | Diesel | 93.4% | 86.8% | 83.9% | **1.00** | **2.00** |
| 26 | Diesel | 97.1% | 91.1% | 88.1% | **1.00** | **2.00** |
| 52 | Diesel | 99.6% | 98.7% | 98.3% | **1.00** | **2.00** |
| 26 | Regular Petrol | 96.0% | 92.3% | 89.8% | **1.00** | **2.00** |

Mean distance from the winner to the third-ranked lag is exactly 1.00 and
to the fourth exactly 2.00 — the signature of a symmetric hill, where the
ranking must be peak, one neighbour, the other neighbour, then peak ± 2.
Against chance: with nine candidate lags, three randomly chosen would be
contiguous 8% of the time; observed 91%.

**So a small gap does not mean "the method failed to decide" — it means
the hill is broad.** The gap alone was the wrong summary statistic. Window
width controls the hill's steepness (the drop from first to third place is
0.20 at 13 weeks, 0.04 at 52), not its shape.

**This is the real argument for the distributed-lag model (roadmap item
3):** the data's shape is what a distributed lag assumes. And it suggests a
cheap intermediate step — fit a parabola through the top three points and
take its vertex, giving a continuous lag estimate (e.g. "2.4 weeks")
instead of forcing an integer choice between two neighbours.

**Finding 3 — a genuinely flat profile exists, is rare, and is always a
trend artifact.** Windows where `r` varies by less than 0.05 across *all*
lags: 0.9–3.4%. Every single one of them is a *high* plateau — the share
that is both flat and weak (`r_max` < 0.5) is exactly zero in all six
width×fuel cells. A flat profile never looks like "no relationship"; it
looks like "excellent relationship at every lag", which is the most
convincing possible way to be wrong. The cause is unambiguous:

| | crude's correlation with time, within window |
|---|---|
| flat-profile windows | **0.91–0.97** |
| peaked windows | 0.52–0.59 |

A series moving in a near-perfect straight line correlates equally well
with itself at any shift. This is exactly `02_calm_own_refinery` — r=0.96
with a gap of 0.0003 — and explains why that period's lag looks more
authoritative than any crisis period's while meaning less.

**Finding 3 — a real shift at the 2022 boundary, which cannot be attributed
to the refinery.** Splitting windows into those falling entirely before
31 Mar 2022 (when Marsden Point stopped refining) and entirely after:

| | windows | lag 0 | lag 1 | lag 2 | lag 3 | 4+ | mean lag | mean lag, decisive windows only |
|---|---|---|---|---|---|---|---|---|
| Diesel, pre | 911 | 165 | **525** | 94 | 51 | 76 | 1.38 | 1.11 |
| Diesel, post | 203 | 17 | 34 | **134** | 2 | 16 | **2.09** | **3.28** |
| Regular Petrol, pre | 911 | 184 | **496** | 119 | 49 | 63 | 1.34 | 1.49 |
| Regular Petrol, post | 203 | 26 | **86** | 71 | 6 | 14 | 1.67 | 1.72 |

Diesel's modal lag moves from 1 (58% of windows) to 2 (66%); petrol's does
not move at all. Tempting, and wrong to attribute: **MBIE switched its
retail price source from Envisory to Datamine on 1 Jan 2022**, 13 weeks
earlier, and that switch left two measurable fingerprints in the price
series — weeks with an unchanged price stop entirely after 24 Dec 2021,
and diesel's value precision changes while petrol's does not
(`mbie_notes.md`). The confound is *asymmetric by fuel in the same
direction as the effect*, which is the worst possible case. A 26-week
window cannot separate two events 13 weeks apart, so this design cannot
attribute the shift either way.

Two caveats on the arithmetic above: overlapping windows are not
independent observations (26-week windows stepped weekly means roughly 35
independent windows pre-2022 and 8 post, not 911 and 203), and the target
is bounded by the window, so `n` shrinks as the lag grows — the same
convention as `lag_correlation`, kept for comparability.

## Refreshing the published report — the service could never do it until 13 Aug 2026

Report 1 lives in **My Workspace** as an **import** model (confirmed via
`INFO.VIEW.TABLES()`: every table reports `StorageMode = Import`), so its
data is a snapshot held inside the model. It does not follow the warehouse
— a bronze reload plus `dbt run` leaves the report showing last week's
numbers until the model itself is refreshed.

Until 13 Aug 2026 the service had **never** refreshed it: refresh history
was empty and scheduled refresh was disabled. The data got there by
publishing from Power BI Desktop, which loads rows locally and uploads them
together with the model — the service never needs a connection to the
source for that, which is exactly why the missing connection went unnoticed
for so long.

**`Refresh now` failed with `Premium_ASWL_Error`:**

```
this semantic model uses a default data connection without explicit
connection credentials. Please replace the default data connection ...
with an explicit cloud or gateway data connection.
```

The model reached the warehouse through a *default* connection. Two things
make this awkward to diagnose:

- The **Data source credentials** section in the model's Settings is greyed
  out, which reads as a permissions problem. It isn't — the binding lives
  in **Gateway and cloud connections**, a different section on the same
  page. Ownership was never the issue (`configuredBy` matched the
  signed-in account, `isOnPremGatewayRequired: false`).
- `GET /datasets/{id}/datasources` returns no `datasourceId` and no
  `gatewayId` when the connection is default. That is the fastest way to
  tell the two states apart — a properly bound model returns both.

**Fix:** create a ShareableCloud connection (type `SQL`, auth `OAuth2`,
privacy `Organizational`) against the warehouse endpoint, then map it to
the model under Gateway and cloud connections. After that `Refresh now`
completed in about five seconds and the model picked up the new week.

### Two models named `nz_fuel` — the trap that cost the most time

There were **two** semantic models and two reports carrying the same name:
one pair in My Workspace, one pair in the `nz-fuel-price-project`
workspace. Both reports were published to web — the old Fabric-workspace
embed code described as "dead and should be deleted" earlier in this
document had in fact never been deleted, so two public links existed,
backed by two different models.

What that cost on 13 Aug: the cloud connection was bound to the wrong
model, and a successful refresh updated a report nobody was looking at
while the public link stayed a week stale. The names are identical in the
UI; the only reliable discriminator is the URL — **`groups/me` means My
Workspace**, anything else is the project workspace. `GET /myorg/reports`
versus `GET /myorg/groups/{id}/reports` separates them unambiguously and is
worth preferring over clicking.

**Cleaned up 13 Aug 2026:** the report and the semantic model in the
`nz-fuel-price-project` workspace were both deleted, leaving exactly one
publish-to-web artifact (verified via
`/admin/widelySharedArtifacts/publishedToWeb`, which now returns a single
entry). A pbix backup of the deleted report was exported first, to
`~/nz-fuel-price-project/nz_fuel_projectws_backup_20260813.pbix` — outside
the repo.

### Weekly sequence from here

`resume capacity → run ingest_mbie_weekly → dbt snapshot → dbt run
--full-refresh → dbt test → refresh the semantic model`.

The model refresh reads the warehouse, so it needs the capacity **up**.
Viewing the report afterwards does not, since import mode serves from the
model — which is the whole point of the My Workspace arrangement described
above. Scheduled refresh is now technically possible, but it would have to
fire inside the window when the capacity happens to be running (it
auto-pauses at 23:00 NZT and is resumed by hand), so it is left disabled
rather than half-working.

## Levels vs changes — the project has always correlated levels, and it matters

`lag_correlation_series` feeds raw `dubai_crude_nzd` and `board_price` into
the sums. That is a correlation of **levels**, inherited from the original
R script. Since crude's within-window correlation with time averages
0.57–0.66 across the whole history (see above), every level-based estimate
carries some of that shared drift. Re-running the sweep on **week-over-week
changes** of both series — same macro arithmetic, differenced inputs:

| basis | width | fuel | mean peak r | **mean gap to runner-up** | modal lag |
|---|---|---|---|---|---|
| levels | 26 | Diesel | **0.831** | 0.0313 | 1 |
| changes | 26 | Diesel | 0.599 | **0.1490** | 1 |
| levels | 26 | Regular Petrol | **0.828** | 0.0293 | 1 |
| changes | 26 | Regular Petrol | 0.591 | **0.1421** | 1 |

**The lag is not a trend artifact.** On changes the peak is ~5× better
separated while `r` drops by about 0.23 — the expected signature of a real
timing relationship. Had the lag been an artifact of shared drift,
differencing would have left nothing; instead 80% of windows still peak
above 0.5. Two consequences: the project's published `r` values are
optimistic by roughly 0.2, and the lag itself is better identified on
changes than on levels.

**In the current crisis the two bases disagree, and the disagreement is
informative:**

| fuel | basis | lag 0 | 1 | 2 | 3 | 4 | 5 | 6 | best | slope |
|---|---|---|---|---|---|---|---|---|---|---|
| Diesel | levels | 0.423 | 0.723 | 0.895 | **0.900** | 0.766 | 0.561 | 0.446 | 3 (tied with 2) | 0.976 |
| Diesel | changes | 0.334 | 0.589 | 0.668 | **0.794** | 0.574 | −0.113 | −0.570 | **3** | 0.547 |
| Regular Petrol | levels | 0.441 | 0.787 | **0.923** | 0.860 | 0.714 | 0.522 | 0.437 | 2 | 0.398 |
| Regular Petrol | changes | 0.520 | **0.738** | 0.654 | 0.673 | 0.373 | −0.345 | −0.694 | **1** | 0.324 |

Diesel's lag 3, a coin flip on levels (0.005 over lag 2), wins by 0.126 on
changes. Petrol shortens from 2 to 1. So the fuels differ by more than the
levels view showed — **3 weeks against 1**, not 3 against 2. The retraction
above still stands as written (on levels it *is* a tie); the changes basis
is what breaks the tie.

**The pass-through weights are not additive, and finding that out killed a
shortcut.** The plan was to read distributed-lag weights straight off the
per-lag change slopes and check them against the levels slope. They do not
add up — diesel's lags 0–4 sum to 2.224 against a levels slope of 0.976;
petrol 1.073 against 0.398:

| fuel | lag 0 | 1 | 2 | 3 | 4 | 5 | 6 | sum 0–4 | levels slope |
|---|---|---|---|---|---|---|---|---|---|
| Diesel | 0.291 | 0.515 | 0.545 | **0.547** | 0.326 | −0.057 | −0.233 | 2.224 | 0.976 |
| Regular Petrol | 0.227 | **0.324** | 0.257 | 0.190 | 0.075 | −0.065 | −0.118 | 1.073 | 0.398 |

Each of those is a *separate univariate* regression, and weekly crude
changes are autocorrelated — a move persists for several weeks — so each
lag's slope claims the same market move. Summing them counts it repeatedly.
Real weights require one **joint** regression of the price change on crude
changes at all lags simultaneously, which the current sums-based macro
(`ΣX, ΣY, ΣXY, ΣX², ΣY²` — enough for exactly one regressor) cannot
express. This is the concrete reason ADL is a new model rather than a macro
edit, and it likely belongs in Python rather than T-SQL.

**What the shapes still say, comparably, without being summed:** diesel's
profile is a plateau (0.29 / 0.52 / 0.55 / 0.55 / 0.33 — spread over three
to four weeks), petrol's is a spike at lag 1 (0.23 / 0.34 / 0.26 / 0.19 /
0.07). A forecast that applies one lag's slope therefore captures most of
petrol's response and only part of diesel's — which predicts under-shooting
on diesel and accuracy on petrol, matching what the backtests showed.

**Defect in the backtest record:** the table above logs error *magnitudes*
(4.6%, 7.3%, 0.4–0.9%) and "direction correct", but not whether the
forecast came in over or under. That sign is the most diagnostic part and
should be recorded on the next run.

## The forecast measure multiplies a change by a slope fitted on levels

Report 1's forecast is `current_price + resolved_slope × (crude_now −
crude_lag_weeks_ago)`. The multiplicand is a **change**; `resolved_slope`
comes from a regression on **levels**. Fitting the same relationship the
way the formula actually uses it — crude change over the past k weeks
against the price change over the next k weeks, k = each fuel's own
resolved lag, `06_iranus_2026`:

| fuel | k | n | slope fitted on k-week changes | r | `resolved_slope` (levels) | ratio |
|---|---|---|---|---|---|---|
| Diesel | 3 | 17 | 0.583 | 0.801 | 0.9755 | **1.67×** |
| Regular Petrol | 2 | 19 | 0.233 | 0.839 | 0.3984 | **1.71×** |
| Premium 95R | 2 | 19 | 0.235 | 0.833 | 0.4019 | **1.71×** |

The published coefficient is inflated by about 70%, consistently across all
three fuels — a property of the levels fit, not of any one fuel.

**Replaying the formula week by week over the current crisis** (17 diesel
forecasts, 19 per petrol grade) reproduces the documented backtest errors —
mean absolute error 6.7% of price for diesel and 1.9–2.0% for the petrols,
against 4.6–7.3% and 1.7–1.9% in the table above — so the simulation is
measuring the same thing the backtests did. It also settles the direction:
prices were mostly falling, and the formula **under-predicts the size of
the fall**, by 2.23 c/L on average for diesel and ~1.1 for the petrols.

An inflated slope that under-predicts looks contradictory until you notice
the formula has no intercept: it assumes price does not move when crude
does not. Price drifted downward on its own through this period, and the
oversized slope was partly standing in for that drift. Comparing three
variants on identical weeks:

| fuel | current formula | fitted slope, no intercept | fitted slope + intercept |
|---|---|---|---|
| Diesel | MAE 20.91 | 16.08 | **12.85** (intercept −7.91) |
| Regular Petrol | 6.40 | 4.79 | **4.44** (intercept −1.72) |

So correcting the slope alone **improves** the forecast by 23–25%; adding
an intercept gets to −39% for diesel. Two cautions before anyone acts on
that second column: the intercept is fitted in-sample, and it encodes
"the drift continues", which is exactly the assumption that breaks at a
turning point. The slope correction carries no such baggage.

**Defect in the backtest record:** the table above logs error *magnitude*
and "direction correct" but not whether the forecast came in over or under.
That sign is the most diagnostic part of a backtest and had to be
recovered by re-simulation. Record it next time.

## Pass-through, decomposed — and three versions of an asymmetry finding that did not survive

The question this section was opened to answer is what the pump price is
made of and when that changes, not how to fix the forecast.

**Three candidate findings died on the way, all to the same class of
check.** Recording them because each looked solid at the point it was
written:

1. *"The asymmetry reversed sign after the refinery closed"* — pre-2020
   prices responded ~2× more strongly to crude falls, the import era ~2×
   more strongly to rises. Killed by matching on move size: the import era's
   average weekly crude move is 5.75 against 2.96 pre-2020, and restricting
   both eras to moves of 2–8 removes the reversal entirely.
2. *"Falls pass through more than rises"* (and its mirror) — the **sign of
   the asymmetry depended entirely on whether an estimated drift was
   subtracted**, because the drift is positive and subtracting it
   necessarily strengthens falls and weakens rises. A result that flips on
   an analyst's choice is not a result.
3. *"Small crude moves barely pass through"* — an artifact of fitting
   slopes inside narrow ranges when the crude series is rounded to whole
   dollars (`mbie_notes.md`). Ratios of means, which are robust to that
   rounding, show no such gradient.

The fix for (2) was to stop estimating the drift and remove its known
cause instead: the target becomes `board_price − taxes − gst − ets`, which
strips the policy-driven component and, unlike `price_excluding_tax`, does
not import the quarterly re-basing steps. On that target the early-era
asymmetry nearly vanishes (diesel 0.76 down vs 0.84 up, raw).

**What survives, measured at four horizons so that nothing rests on one
window.** Response is c/L per NZD/bbl of crude move, cumulative over the
horizon:

| fuel | era | horizon | cost response ↓/↑ | margin response ↓/↑ | price response ↓/↑ |
|---|---|---|---|---|---|
| Diesel | import | 2w | 0.554 / 0.762 | 0.141 / 0.127 | 0.692 / 0.886 |
| Diesel | import | 3w | 0.752 / 1.013 | 0.222 / 0.264 | 0.978 / 1.278 |
| Diesel | import | 4w | 0.929 / 1.100 | 0.267 / 0.440 | 1.204 / 1.542 |
| Diesel | import | 6w | 1.031 / 1.037 | 0.442 / 0.621 | 1.490 / 1.653 |
| Regular | import | 3w | 0.466 / 0.481 | 0.260 / 0.336 | 0.723 / 0.806 |
| Regular | import | 6w | 0.555 / 0.437 | 0.472 / 0.587 | 1.034 / 1.007 |
| Diesel | pre-2020 | 3w | 0.434 / 0.347 | 0.167 / 0.259 | 0.759 / 0.841 |
| Regular | pre-2020 | 3w | 0.478 / 0.375 | 0.216 / 0.280 | 0.861 / 0.905 |

**1. Diesel's landed cost is 1.5–2.4× more crude-sensitive than petrol's,
at every horizon — but only in the import era.** Pre-2020 the two fuels are
nearly identical (0.39 vs 0.37). The divergence appears after the country
switched from refining crude to importing finished product, and it sits on
the **cost** side, before any retailer decision. This is the best available
explanation for why diesel has behaved differently throughout this project,
and it needs no behavioural story: gasoil and gasoline are different
products with different crack spreads.

**2. Importer margin moves *with* crude in all 32 cells measured, and the
effect grows with horizon** — diesel upward: 0.127, 0.264, 0.440, 0.621 at
2, 3, 4 and 6 weeks. Margin is not a buffer absorbing crude swings; it is
an amplifier, and the amplification accumulates the longer a move persists.
Roughly a third of the price response beyond landed cost is margin.
*Caveat:* `Importer margin` is the residual of MBIE's cost model, so this
is a measured property of the series, not proof of importer behaviour.

**3. Diesel's remaining up/down asymmetry is inherited from the cost side,
not created at the pump.** Cost responds more to rises than falls at short
horizons (0.762 vs 0.554 at two weeks) and converges by six (1.037 vs
1.031); the price asymmetry narrows in step. Whatever "rockets and
feathers" exists here originates upstream — in the Singapore product market
or in MBIE's cost construction — not in retailer pricing.

**Two measurement caveats attached to the numbers above.** Overlapping
horizons mean roughly a third of the nominal observations are independent
(n≈100 per cell in the import era). And in the pre-2020 era the
board-derived target carries about 0.25 of adjustment-factor co-movement
with crude, so those price responses are overstated by that much; in the
import era the residual is zero.

## What a litre is actually made of, in cents

Accounting only — no fitting. Uses `adjusted_retail_price`, which is where
MBIE's identity closes (`mbie_notes.md`). Week of 7 Aug 2026:

| component | Regular Petrol | share | Diesel | share |
|---|---|---|---|---|
| Importer cost | 126.3 | 41.9% | 172.2 | **63.6%** |
| Importer margin | 45.7 | 15.1% | 47.6 | 17.6% |
| Taxes and levies | 77.3 | 25.6% | **0.9** | **0.3%** |
| ETS | 13.1 | 4.3% | 14.7 | 5.4% |
| GST | 39.3 | 13.0% | 35.3 | 13.0% |
| **Total** | **301.7** | | **270.8** | |

**Diesel carries almost no fuel tax** — 0.9 c/L against petrol's 77.3,
because diesel vehicles pay Road User Charges separately. Two-thirds of a
diesel litre is the commodity, against 42% for petrol, whose price is 43%
tax and therefore structurally damped. This is a cleaner explanation for
"diesel behaves differently" than anything behavioural, and it compounds
with the cost-side finding above.

## What actually drove pump prices through the 2026 crisis — it is not margin

**Corrected 14 Aug 2026, and the correction reverses the conclusion.** The
first version of this section used 6 Mar 2026 as the pre-crisis baseline
because it is the first observation *inside* `06_iranus_2026`. It is not a
baseline: by 6 Mar crude had already run 119 → 146 and diesel's modelled
cost had jumped 52 c/L in that one week. The correct baseline is the last
observation **before** the period, 27 Feb.

| diesel | 27 Feb (pre-crisis) | 20 Mar (crude peak) | 7 Aug (latest) | net |
|---|---|---|---|---|
| Crude, NZD/bbl | **119** | 267 | **131** | **+10%** |
| Importer cost | 106.7 | 234.5 | 172.2 | **+65.5** |
| Importer margin | **42.4** (84th pct) | 2.7 (0.3rd) | 47.6 (92nd) | **+5.2** |
| Taxes + GST + ETS | 38.2 | 49.1 | 51.0 | +12.8 |
| Board price | 188.2 | 287.3 | 271.7 | **+83.5** |

**Crude is not below its pre-crisis level; it is 10% above it.** And the
83.5 c/L rise in diesel decomposes as **cost +65.5 (78% of it), margin +5.2
(6%), taxes and GST +12.8 (15%)**. Petrol's 48.8 c/L rise: cost +32.7
(67%), margin +8.1 (17%), taxes +8.0 (16%).

The withdrawn version claimed margin supplied roughly two-thirds of the
increase. That was entirely an artifact of starting the clock a week into
the shock, when margin had already been crushed to −2.2: measuring the
recovery from an artificial trough and calling it the crisis.

**Margin was already high before the crisis** — 84th percentile for diesel,
91st for petrol — was crushed to the 0.3rd and 1.1st at the cost peak, and
has returned to the 92nd and 98th. So: a deep dip and a recovery to
slightly above where it started, not a rise from nothing. The compression
episode is real and remains the most striking single fact; the net
contribution to today's price is small.

**The real driver is the spread between crude and refined product.** Cost
per unit of crude:

| | 27 Feb 2026 | 7 Aug 2026 | change |
|---|---|---|---|
| Diesel | 0.897 | **1.314** | **+46%** |
| Regular Petrol | 0.787 | 0.964 | +23% |

Crude rose 10% while diesel's landed cost rose 61%, both in NZD, so this is
not currency. Whatever sits between crude and a delivered litre — refining
margin, freight, insurance — widened enormously, and for a Middle East
crisis that is what one would expect. None of it is visible in this
dataset: freight enters MBIE's cost model as a quarterly constant, and the
product price is not published at all. **A model with crude as its only
factor cannot see the thing that moved the price.** This is now the
strongest argument for the Singapore product series in roadmap item 2.

**This also reconciles the two horizon results above.** Over 2–6 week
horizons margin moves *with* crude; across the phases of this crisis it
moved *against* it, deeply. Both hold: a cost jump compresses margin
immediately and the recovery arrives later.

*Caveat:* the April extremes (diesel cost 290.9 against crude 170 on 17
Apr, a ratio of 1.71) fall inside the 18 Mar – 1 Jul window that MBIE
reconstructed retroactively.

**A public prediction that came true, worth recording as evidence the
method has some forward content.** Part 1 (published ~24 Jul 2026) stated
that crude had risen on 17 July with no pump movement yet, and that "if the
two-week pattern still holds, we should begin seeing that change around the
end of July". Board prices: 243.0 on 17 Jul, then **+9.4 on 24 Jul and
+13.4 on 31 Jul** for diesel (+1.5 and +6.6 for regular petrol). The turn
landed exactly in the predicted week.

## The distributed-lag model, first results — 15 Aug 2026

`research/adl_baseline.py`. Target is the commercial part of the price
(`adjusted_retail − taxes − gst − ets`), factor is `Δimporter_cost`, sample
is the import era (228 weeks from Apr 2022), errors are Newey–West with
bandwidth K+2. Lag length K chosen by BIC, with the rule fixed before
looking at output. Both differenced series are stationary (ADF p < 0.0001).

**The headline, and it is robust.** For petrol, total pass-through is
complete and no more: 0.92–1.03 at every K from 3 to 12, with the 95%
interval covering 1.0 throughout. A 1 c/L rise in landed cost arrives in
full at the pump — 1.15 c/L with GST — and none of it is permanently
retained as margin. That is a real answer to the question the project
exists to ask, and it did not need a single-best-lag estimate to get there.

**Shape.** The peak is at lag 1 for both fuels, and **69–85% of the total
arrives within three weeks**. Petrol's centre of mass is 1.24–1.93 weeks,
diesel's 1.19–3.03.

**The joint fit confirms the double-counting diagnosis numerically.**
Diesel's separate per-lag regressions summed to 2.22 against a levels slope
of 0.98 (`analyses/lag_levels_vs_changes.sql`). Fitted jointly, the same
lags sum to 0.9–1.2. Roughly half of the old number was neighbouring lags
claiming the same market move.

**Superseded 15 Aug 2026 — see "Scoped correctly" below. The instability
is not diesel's, it is the high-volatility weeks'.** The paragraph is kept
because the reasoning that follows it is still how the problem was found.

**Diesel's total is not identified, and this must be reported with any
number taken from it.** It climbs monotonically with the lag length —
0.833, 0.879, 0.894, 1.045, 1.117, 1.213 at K = 3, 4, 6, 8, 9, 12 — so
"diesel passes through more than 100%" is available to anyone willing to
choose K = 9 or above, and "less than 100%" to anyone choosing K ≤ 6. BIC
picks 9. Petrol shows no such drift, which is why its result stands.

The same K-dependence undermines a long-standing project belief: **"diesel
is slower than petrol" is not robust either.** At a common K of 3, 4 or 5
*petrol* has the later centre of mass (1.45–1.59 vs 1.19–1.43); the
ordering only flips at K ≥ 6. Compare centres of mass only at a common K,
and state the K.

**What the creep is: the 2026 crisis, and nothing else.** Found on the
fourth attempt, after seasonality, error correction and self-echo in the
cost series were each tested and failed. Excluding the 23 crisis weeks
collapses diesel's spread across K = 3…12 from **0.380 to 0.056**, and
leaves the total at 0.87–0.99 at every K — stable, and indistinguishable
from petrol's 0.89–1.00 on the same sample. The significant late weights go
with it: lag 8 runs +0.105 (t 3.6) and lag 9 +0.084 (t 4.6) on the full
sample, against −0.019 (t −0.4) and +0.037 (t 0.8) with the crisis removed.
Petrol shows a much weaker version of the same thing (+0.053, t 2.7 →
+0.032, t 1.3).

The intermediate hypotheses died as follows, and are recorded because each
looked reasonable: month dummies move the totals by ≤0.03; an explicit
error-correction term leaves the spread at 0.373; and diesel's cost changes
have autocorrelation of +0.021 and −0.059 at lags 8 and 9, against a ±0.132
band — no echo to pick up. The raw cross-correlation at those lags (+0.018,
+0.069) is not individually significant either; the regression manufactures
significance by conditioning on the other lags.

**Two readings, and 23 weeks cannot separate them.** Either an episode with
roughly ten times the usual variance dominates a least-squares fit far
beyond its 10% share of the rows and manufactures long-lag structure, or
pass-through genuinely runs longer and overshoots during a crisis. The
second is an economic claim worth testing, and it is exactly what roadmap
step 7 was designed for — which now has a specific target instead of a
general intention.

Note the awkwardness this creates for the project's premise: crises are
where the lag was always said to be identifiable, and the crisis is also
what destabilises the estimate. Both can be true — a crisis has the signal
*and* the leverage — but any crisis-period number needs the non-crisis
number printed next to it.

**What the creep is not: seasonality.** Diesel's margin is about twice as
seasonal as petrol's (month deviations from the annual mean span 6.07 c/L
against 3.17, trough in March, peak in May). Adding month dummies to the
model moves the totals by at most 0.03 and leaves the climb across K
intact. Hypothesis tested and dead; the standard errors do tighten
slightly, so the dummies are worth keeping as noise control. The remaining
candidate is the missing error-correction term.

**`importer_cost` is decisively the better factor for petrol** — R² 0.845
against crude's 0.678 on the identical specification. For diesel the gap is
small (0.840 vs 0.794), which is consistent with diesel's landed cost being
more crude-sensitive to begin with.

### Scoped correctly: it is the volatile weeks that are unidentified, not diesel

The parallel labelling thread (`docs/period_labelling.md` §7,
`seeds/period_flags.csv`) replaced the hand-drawn crisis/calm periods with
a measured `crude_vol_regime`, and that reframes the result. **Replicated
here independently, with separate code, before being adopted:**

| diesel, spread of total across K=3…12 | normal weeks | high-volatility weeks |
|---|---|---|
| import era (27 high weeks) | 0.123 | 0.450 |
| 2010+ (109 high weeks) | 0.122 | 0.474 |

Two samples of very different size, near-identical shape. Normal weeks
settle by K≈5 and stay at 0.87–1.03; high weeks track them to K=6 and then
climb away, reaching ~1.35 at K=12. The peer's own figures (0.143/0.524 and
0.148/0.431) differ in the third digit and agree completely in shape.

**The honest statement is therefore narrower and stronger than "diesel is
not identified":** non-crisis pass-through is stable and complete for both
fuels; the *crisis* sum is the part that is not identified. The headline
result survives, scoped.

Three artifact explanations were ruled out by the labelling thread, and
each is one this thread would otherwise have had to run:

- **Not a generic block effect.** Dropping each of the 189 contiguous
  27-week blocks in turn, the 2026 window ranks 2nd of 189 by resulting
  spread; the top five are the same window ±2 weeks. Removing only its
  first half *raises* the spread to 0.680 — worse than either keeping or
  dropping the episode whole.
- **Not leverage.** High weeks carry 5× the factor variance (sd Δcost 14.9
  vs 3.0), but weighting by inverse local crude variance gives 0.380
  against OLS's 0.390.
- **Not degrees of freedom.** At K=12 the import era offers 27 high weeks
  for 13 coefficients; on 2010+ there are 109 (8.4 per parameter) and the
  climb is essentially unchanged.

**Still open:** whether the high-regime climb is a genuinely longer
response or an artifact of something not yet named. Factor autocorrelation
is the obvious candidate and fits badly — in high weeks Δcost autocorrelates
at 0.17 and 0.26 at lags 1–2, and near zero or negative at lags 3–7, which
is exactly where the climb happens.

**Consequence for sampling.** There is no second crisis in the import era
to test against: `04_tariff_2025` was mislabelled, and crude actually fell
9.8% across it, with no week clearing the volatility threshold at any
setting. Dropping it moves the spread from 0.383 to 0.387 — it has no
leverage because it contains no shock. Estimating the crisis regime
therefore means going back to 2010+, where the `data_regime` axis absorbs
the 2022 measurement break as a dummy.

**This also puts an older finding in doubt.** "Lag stability separates
crisis from calm" was computed against the hand-drawn `periods.csv`, which
labelled 2025 a crisis when it was not. That finding needs recomputing
against `crude_vol_regime` before it is quoted again.

### Error correction: real, measurable, and not the explanation for diesel

`research/adl_ecm.py`, 15 Aug 2026. The term is the margin's distance from
its own trailing mean, lagged one week — trailing, because margin levels
have tripled since 2004 and a fixed centre would measure that drift.

**It exists.** The coefficient is negative and significant for both fuels
at every window tried (52, 78, 104 weeks): petrol −0.084 to −0.109 (HAC t
−2.74 to −2.94), diesel −0.096 to −0.122 (t up to −4.30). **Roughly 8–12%
of a margin gap closes per week; half of it within about six weeks.** When
margin sits below its normal level, the pump price rises by more than the
cost change alone accounts for — which is what was watched happening after
March 2026, and is now a number rather than an anecdote.

**The pre-registered prediction failed.** Diesel's total was predicted to
stop creeping with lag length once error correction was stated explicitly.
The spread from K=3 to K=12 was 0.380 before and is 0.373 after. Second
hypothesis dead, after seasonality. Diesel's creep remains unexplained.

**Do not read the ECM's lag weights as pass-through.** Adding the term
drops the sum from 0.92–1.03 to 0.80–0.91 for petrol, and the temptation
is to conclude pass-through is really 85%. That would be wrong for a
structural reason: equilibrium in this specification is `margin = normal`,
i.e. `net − cost = const`, which *is* unit pass-through. **The
specification imposes what the baseline freely estimates.** So the ECM's
lag sum is only the fast component — about 85% arriving through direct cost
response, the remaining ~15% seeping in through margin recovery over the
following weeks — and the test of completeness remains the baseline, which
does not impose it and returned ~1.0 for petrol.

Testing long-run pass-through *properly* needs a free coefficient on cost
inside the equilibrium relation (`net − θ·cost − c`), estimated rather than
fixed at θ = 1. That is a cointegration test and is the natural refinement
if the question is ever pressed.

### Petrol and diesel are not two instances of the same thing

Prompted by the question of whether their different behaviour has a
different customer base behind it — diesel goes to trucking, farming and
fishing, petrol to private cars.

- **Discounting differs, and collapsed.** `board_price − adjusted_retail`
  ran ~2 c/L for both fuels in 2010, peaked at 14.8–18.3 (petrol,
  2017–2020) and 15.6–16.4 (diesel, 2017–2019), and has fallen to 2.89 and
  0.99 by 2026. Petrol's discount is the deeper one in most years, which
  fits consumer loyalty schemes. **Caveat that blocks attribution:** the
  collapse coincides with MBIE's retail-source change on 1 Jan 2022, so the
  end of the discount era and a measurement artifact cannot be separated
  here.
- **Diesel's price is stickier than its cost.** In the import era diesel's
  board price is unchanged (|Δ| < 0.5 c/L) in 22.8% of weeks against
  petrol's 20.2%, while diesel's *cost* is unchanged in only 10.5% against
  petrol's 13.2%. A noisier input and a quieter output.
- **The seasonality probably points upstream, not at NZ customers.**
  Diesel's margin troughs in March and peaks in May. That is the signature
  of northern-hemisphere winter gasoil demand raising the Singapore quote —
  which `importer_cost` tracks immediately while the pump price lags — not
  of the New Zealand agricultural cycle.
- **The contract/bulk channel is invisible here, so the hypothesis cannot
  be closed.** MBIE monitors service-station prices. Tanker deliveries to
  farms, marine bunkering and site fuel are a separate commercial channel
  and are not evidently in this series, yet plausibly account for much of
  national diesel volume. Nothing in this dataset can confirm or refute a
  contract-pricing explanation.

## n = 1. Every crisis claim in this project rests on one episode

Established 15 Aug 2026 from `seeds/period_flags.csv`, and it reframes
everything above that carries the word "crisis". The measured volatility
regime finds nine episodes in 22 years. Crude in NZD, start to end, with
the within-episode range as (max−min)/min:

| episode | crude NZD/bbl | net | range | direction |
|---|---|---|---|---|
| 2004_run_up | 47 → 49 | +4.3% | 9% | up |
| 2008_gfc_crash | 160 → 98 | −38.8% | 63% | down |
| 2009_rebound | 71 → 86 | +21.1% | 34% | up |
| 2015_glut_onset | 73 → 77 | +5.5% | 38% | up |
| 2016_glut_trough | 69 → 61 | −11.6% | 87% | down |
| 2016_opec_cuts | 60 → 67 | +11.7% | 21% | up |
| 2020_covid_crash | 85 → 63 | −25.9% | **203%** | down |
| 2022_ukraine | 138 → 155 | +12.3% | 25% | up |
| **2026_iran_us** | 110 → 131 | **+19.1%** | **143%** | **up** |

**Peak-to-trough range is length-dependent and must not be compared across
episodes of different length on its own** — a 27-week window has more
opportunity to accumulate a wide range than a 10-week one. Length-neutral
measures, weekly % changes in crude:

| episode | weeks | sd of weekly change | worst single week | worst 8-week move |
|---|---|---|---|---|
| calm weeks (baseline) | — | 3.2% | 10.9% | — |
| 2022_ukraine | 10 | 7.8% | 12.7% | 44.2% |
| 2020_covid_crash | 19 | 15.7% | 46.7% | 117.2% |
| **2026_iran_us** | 27 | **13.2%** | **39.7%** | **147.2%** |
| 2026, first 10 weeks only | 10 | **18.4%** | 39.7% | 147.2% |

**There has never been another large upward shock in the usable record.**
Against Ukraine 2022 — the obvious mental comparator — 2026 runs 1.7× on
weekly sd across the full episodes, 2.4× on a like-for-like first-ten-weeks
basis, and 3.1× on the single worst week. Crude went 110 → 267 NZD/bbl
against Ukraine's 138 → 173.

The only episode of comparable violence is the 2020 COVID crash, which runs
the other way and belongs to a global demand collapse with lockdowns — not
a supply shock at all. The next largest, the 2016 glut trough, is also
downward. Among *upward* episodes 2026 has no competitor: the closest is
the 2009 rebound at 7.5% weekly sd against 13.2%.

The range comparison quoted first (143% against 25%, 5.6×) survives the
length correction, because 2026's entire range occurs inside its own first
ten weeks — but that was luck, not method, and the length-neutral figures
above are the ones to quote.

By era it is starker still. The import era (Apr 2022+) contains 31
high-volatility weeks in nominally two episodes, but `2022_ukraine` runs
18 Feb – 22 Apr 2022 and only its four-week tail falls inside. **In
practice: one crisis, still in progress.** Widening to 2010+ buys 109 weeks
across six episodes, of which four are downward or small.

**So the failure to identify crisis pass-through is not a methods problem.**
It is n = 1 for the phenomenon of interest, and no estimator repairs that.
Longer lag windows, better standard errors and regime interactions all
describe the same single episode more elaborately.

Three consequences that should govern how this project speaks:

1. **Any sentence of the form "in a crisis, prices…" is a sentence about
   February–August 2026.** Say so.
2. **The comparison set for 2026 is mostly downward shocks.** Using them to
   calibrate expectations for an upward one assumes the symmetry that
   `research/adl_asymmetry.py` could neither find nor rule out.
3. **This retroactively justifies the doubt** raised on 14 Aug about
   whether past crises behaved the same way. They may or may not have; the
   data cannot say, because there is no past crisis of this kind to check.

## Rockets and feathers, fourth attempt: still not there

`research/adl_asymmetry.py`, 15 Aug 2026. Rises and falls estimated in the
**same** regression — `pos = max(Δcost,0)`, `neg = min(Δcost,0)`, separate
weights at every lag — so they share a sample, a target and an error term,
and the difference between them gets a standard error rather than an
eyeball. That is what the three earlier attempts lacked: two died to range
restriction between separately-drawn up and down samples, one to
measurement error in a rounded factor. 2010+, K=6, ECM term included,
`data_regime` dummy, 861 weeks (≈445 up, ≈416 down).

| | rises | falls | difference | block-bootstrap 95% CI | p |
|---|---|---|---|---|---|
| petrol, total | 0.791 | 0.739 | +0.052 | [−0.19, +0.33] | 0.61 |
| diesel, total | 0.713 | 0.423 | +0.291 | [−0.11, +0.53] | 0.20 |
| petrol, centre of mass | 0.76 wk | 1.27 wk | −0.51 | [−1.36, +0.95] | 0.48 |
| diesel, centre of mass | 0.90 wk | 0.24 wk | +0.66 | [−1.29, +4.97] | 0.49 |

**No asymmetry detected, on either measure, for either fuel.** Stated as
pre-registered: *not detected*, not *disproven*.

Two methodological points worth keeping:

- **The HAC Wald test and the block bootstrap disagree, and the bootstrap
  wins.** Diesel's total difference is p = 0.062 by HAC — the sort of
  number that gets written up as "marginal evidence of rockets and
  feathers" — and p = 0.204 under a 12-week block bootstrap. The bootstrap
  respects the serial dependence more completely. Where they disagree in
  this project, prefer the bootstrap.
- **Centre of mass is a ratio and inherits the denominator's noise.**
  Diesel's fall-side total is 0.423 ± 0.192, a 45% relative error, so its
  0.24-week centre of mass is not an estimate of anything. The individual
  lag contrasts do reach significance (diesel lag 0 favours falls, t −3.05;
  lags 1 and 2 favour rises, t +2.87 and +2.36) — but a pattern that
  cancels to nothing in the total is a shape difference at best.

**Power, stated honestly.** The intervals are about ±0.26 for petrol and
±0.32 for diesel, so an asymmetry large enough to matter for a consumer —
say a quarter of a cost rise being retained that a fall is not — would have
been visible. Anything smaller would not. Four attempts with progressively
better methods have now failed to find rockets and feathers in this data;
that is evidence of absence at that magnitude, and silence below it.

## Walk-forward test — the first number in this project that is a forecast

`research/backtest.py`, 15 Aug 2026. Every method refit at every cutoff on
data up to that week only, 2010+, 703 forecast weeks per fuel. Target is
the **pump price**, so the model carries its own conversion
(`×1.15` for GST, ETS assumed unchanged) and is charged for its errors.
Threshold fixed before running: beat "the price won't move" on MAE at two
weeks, outside crisis weeks.

MAE in c/L on the pump price, non-crisis weeks:

| | naive | full-pass rule | Report 1-style | ADL | ADL+ECM |
|---|---|---|---|---|---|
| petrol, 1 wk | 1.934 | 2.090 | 2.443 | 1.453 | **1.420** |
| petrol, 2 wk | 3.519 | 3.473 | 3.552 | 2.796 | **2.743** |
| petrol, 3 wk | 4.832 | 4.991 | 4.610 | 4.069 | **3.970** |
| diesel, 1 wk | 1.893 | 2.165 | 2.624 | 1.421 | **1.372** |
| diesel, 2 wk | 3.440 | 3.529 | 3.436 | 2.669 | **2.650** |
| diesel, 3 wk | 4.739 | 4.933 | 4.439 | 3.917 | **3.842** |

**Passed: 20–27% better than naive**, consistently across both fuels, all
three horizons and both regimes, beating naive in 59–65% of individual
weeks. In crisis weeks the relative gain holds (~20%) on absolute errors
two to three times larger. Accuracy decays with horizon as the structure
requires — the h-week forecast may only use lags k ≥ h — which is also the
check that no future data is leaking.

**Report 1's formula is worse than doing nothing at one and two weeks.**
2.443 against naive's 1.934 for petrol at h=1, 26% worse; level-pegging at
h=2; ahead only at h=3. It beats naive in 39% of weeks — worse than a coin.
The reconstruction is generous to it, too: it refits the lag and slope on a
trailing 26-week window, whereas the deployed measure takes them from the
*current period*, and periods are drawn with hindsight. **A
period-conditioned measure cannot be backtested honestly at all**, which is
itself a finding about its design.

**The simple rule adds nothing** — "the last h weeks of cost change arrive
over the next h" wins 44–50% of weeks, a coin toss. So the value is not in
knowing that pass-through is complete; it is in the *distribution across
weeks*. That is what the joint fit buys, and it is the justification for
the whole ADL apparatus.

**ECM helps slightly and consistently**, 1–3 percentage points at every
cell — the margin's distance from normal carries real forecast information,
which is the practical face of the error-correction result above.

Honest about magnitude: at two weeks the error falls from 3.5 to 2.8 c/L.
A typical two-week pump move is ~3.5 c/L and the model accounts for about a
fifth of it. This is a real edge, not precision forecasting, and should
never be presented as the latter.

Three caveats that travel with these numbers:

- **Revisions cannot be undone.** The panel is the current vintage, so
  "data available at t" already contains MBIE's later corrections. Every
  method benefits equally, so the ranking should hold; absolute errors are
  flattered by an unknown amount.
- **K = 6 was fixed using the full sample** rather than reselected weekly —
  a mild look-ahead, kept for stability and noted rather than hidden.
- **The regime split is ex post only.** `crude_vol_9w` is a *centred*
  window (verified: correlation 0.9925 against a centred recomputation,
  0.72 against a trailing one), so it sees four weeks ahead. It splits the
  results; it never enters a forecast.

## Checks that have repeatedly changed the answer

Five questions, each of which has overturned at least one finding in this
project. Run them before writing anything down, not after:

1. **Is the spread comparable?** Correlation collapses when a series barely
   moves, and grows when it swings — this killed the refinery-era
   hypothesis and inflated the era comparison in the asymmetry work. Compare
   slopes rather than `r` across groups, and check the factor's coefficient
   of variation in each.
2. **What is the drift, and is it doing the work?** If a result changes sign
   depending on whether a trend is subtracted, the trend is the finding.
   Prefer removing a known, named component (taxes) over estimating a
   generic one. **A percentile is a yardstick and inherits the drift:**
   `Importer margin` has tripled since 2004, so ranking a level against the
   full history measures inflation in unmodelled downstream costs. The
   error is asymmetric — conservative for a collapse, misleading for a
   normal level (`docs/mbie_notes.md`).
3. **How precise is the input?** Crude is rounded to whole dollars; the
   retail source changed in 2022; some weeks in 2026 were reconstructed
   retroactively. Measurement error in an explanatory variable biases slopes
   toward zero, worst where the signal is smallest.
4. **Is the baseline actually before the thing being measured?** The dates
   in `periods.csv` are *event* dates, so the first observation inside a
   period already contains part of the shock — for `06_iranus_2026` the
   first in-period week is a week in which crude had already moved 27
   NZD/bbl and modelled cost 52 c/L. Any "change since the start of the
   period" must be measured from the last observation **before** the period
   starts. Getting this wrong turned a 6% margin contribution into a
   claimed two-thirds.
5. **Is that claim about the data measured, or read off the wording?**
   MBIE's dictionary calls the crude column a "**spot**" price and marks
   three other columns as weekly averages. The obvious inference — that
   crude is a point-in-time quote — is wrong: against daily Brent, the
   Mon–Fri mean of the stamped week scores r = 0.89 against 0.68 for the
   Friday quote, and a grid search pins the window at exactly Mon–Fri.
   "Spot" names the *price type*, not the sampling frequency. A
   documentation word is a hypothesis, not a measurement, and here one
   external series settled in a single query what re-reading the PDF could
   not (`docs/mbie_notes.md`).

## Roadmap — where this goes next, in priority order

0. **Locate the asymmetry, now that it has been measured (new, 14 Aug
   2026).** The margin work below has a concrete starting point instead of
   a general intention: margin amplifies crude moves in both directions,
   growing with horizon, and diesel's apparent rockets-and-feathers is
   inherited from the cost side. The open question is no longer "is there
   asymmetry" but "at which step of the chain does it arise" — Singapore
   product prices, MBIE's cost construction, or the pump. The first two are
   distinguishable only with an external product-price series (see item 2),
   which raises that item's value.
1. **Margin/asymmetry analysis (still first, but harder than it looked).**
   Uses data already in hand — MBIE publishes `Importer margin` directly,
   no new source needed. **Re-scoped 13 Aug 2026:** the difficulty is not
   writing an asymmetric regression, it is proving that whatever turns up
   is retailer behaviour rather than an artifact of MBIE's cost model.
   `Importer margin` is a residual — `Adjusted retail − Taxes and levies −
   Importer cost` — so every error in the modelled cost lands in it with
   the sign flipped, including quarterly-stale freight, wharfage and
   quality-premium constants (`mbie_notes.md`). Two specific traps:
   correlating margin against anything derived from `board_price` is
   partly tautological, since margin is an accounting component of it; and
   the current crisis's margin values are retroactively reconstructed.
   Plan the falsification step before the analysis, not after.
   `Taxes`/`GST` are policy-set, not market-reactive, and shouldn't be
   folded into a symmetric correlation the way `exchange_rate` was; `ETS`
   could reasonably join the existing symmetric `factors` list, but
   `Importer margin` needs its own asymmetric (up-move vs down-move)
   analysis, not the existing correlation macro. A practical, cheap
   near-term win, revised 13 Aug 2026: turn the expanding-window query into
   a permanent model, but make the **gap** (winning lag's `r` minus the
   runner-up's, per cutoff) the primary signal into `Forecast Confidence`,
   not "lag unchanged over the last N weeks". Run-length over `argmax` is
   the wrong statistic — for diesel it counts coin flips on a tie, and it
   also fires spuriously whenever the dynamic max-lag cap lifts. The model
   must therefore record `max_lag_allowed` per cutoff and mark
   cap-induced transitions as artifacts. This still supersedes the cruder
   "downgrade when `resolved_lag >= 3`" idea, but on a measured basis
   rather than a mechanism that turned out not to be there.
2. **A daily benchmark — partially DONE 15 Aug 2026; the third reason is
   now closed.** The open question was what MBIE's weekly crude number
   *is*: a weekly average or a single-day snapshot. `seeds/brent_daily.csv`
   (FRED `DCOILBRENTEU`, 5,650 rows from 2004-04-23, free, no API key)
   settled it — **it is the Monday–Friday mean of the stamped week**, r =
   0.89 against 0.68 for the Friday quote, with the window pinned by grid
   search. So the feared snapshot-noise bias does not exist, and factor and
   target sit on the same footing. The same load also delivered the
   intra-week range: crude moves more *within* the week than the weekly
   average moves *between* weeks in ~70% of weeks, in every era. Both
   results and their method are in `docs/mbie_notes.md`. **What remains
   open** is (a) the smoothing use below, which needs the daily series
   joined into a model rather than queried ad hoc, and (b) the refresh
   path — the seed is a static hand-downloaded snapshot, not a pipeline.
   **EIA Brent (daily crude benchmark) as a new source.** Solves two
   documented problems at once, which is why it's next rather than a
   generic "add more sources" item: (a) enables the smoothed
   `crude_change` comparison described above — at weekly granularity,
   smoothing only cuts noise by ~30–40% (√N scaling, N=2–3) and risks
   blurring the signal itself since the smoothing window competes with a
   lag that's often only 1–3 weeks; at daily granularity (N≈14 for a
   2-week window) the same smoothing gets ~73% noise reduction without
   that conflict; (b) gives a real, independent read on intra-week crude
   volatility, which MBIE's weekly data structurally cannot show. Note
   Brent ≠ Dubai — a proxy, not a replacement for the existing regression,
   which stays anchored to Dubai crude.

   **Revised 13 Aug 2026 — a refined-product quote beats another crude
   benchmark.** MBIE builds `Importer cost` from Singapore product spot
   prices (Argus: Gasoline 95 RON for petrol, Gasoil 50ppm for diesel),
   not from crude. Dubai crude is therefore one step upstream of what
   actually drives New Zealand's landed cost, with refining margin and its
   own lag in between — and it explains why diesel behaves differently
   from petrol without needing a retailer-behaviour story at all: it
   tracks a different product with a different demand cycle. A Singapore
   product quote is the better new factor; Brent's remaining advantage is
   only daily granularity. Whether an equivalent series is free or
   affordable (Argus is commercial) is the open question — check before
   committing to this item.
3. **Distributed lag model (ADL) — promoted 13 Aug 2026.** Not because
   the search is undecided (that framing was withdrawn — see above), but
   because the profile is a smooth hill over adjacent lags at every window
   width: the effect genuinely arrives spread across neighbouring weeks,
   which is what a distributed lag represents and a single-lag model
   cannot. Requires a joint regression on several lagged crude changes at
   once; per-lag univariate slopes are not additive because crude's own
   weekly changes are autocorrelated. The sums-based macro cannot express
   it, so this likely means Python rather than T-SQL — a tooling decision
   to make deliberately. Cheap intermediate step first: parabolic
   interpolation of the peak from the top three points, giving a
   fractional lag instead of an integer. The deeper, correct fix for the
   assumption baked into `resolved_lag`/`resolved_slope`: that the whole
   effect of a crude move lands at one lag, and that lag/slope are
   constant across an entire period. The diesel work above no longer
   supports the claim that the lag *shifts* mid-period, but it strengthens
   the case for a distributed lag from the other direction: when lags 2 and
   3 fit equally well, the honest reading is that the effect is spread
   across both, which is precisely what a single-lag model cannot express.
   A proper distributed-lag model spreads the effect across several lags
   with different weights instead of picking one "best" lag. Bigger
   undertaking than the rest of this list — a new model, not a patch.
4. **Add `basis` (levels / changes) as a third dimension of
   `lag_correlation`, alongside factor and target.** Same reasoning as
   "Factor and target are both dimensions" above: compute both and know how
   they differ, rather than picking one. Levels stay because the project
   reproduces the R script; changes are the better-identified basis for the
   lag and the correct one for a slope that will be applied to a change.
   **Check first, before anything else here:** Report 1's forecast
   multiplies a crude *change* by `resolved_slope`, which is fitted on
   levels. Whether that is a real error in a published measure is a
   one-query question and should be answered before more analysis is piled
   on top.
5. **Customs / Stats NZ overseas merchandise trade** — monthly petroleum
   import value *and* quantity from Customs entries, which divide out to
   the price actually paid at the border. That is the one thing MBIE's
   replacement-cost series structurally cannot provide, and therefore the
   only visible route to separating shipping time from pricing behaviour.
   Check first whether import values are recorded before or after freight;
   MBIE's `Importer cost` includes it, so a mismatch would make the
   comparison meaningless. MBIE's own monthly oil statistics (supply,
   imports, stock change) are a second source for the same question.
6. **Stats NZ** as a candidate secondary source — mainly useful as an
   independent cross-check of MBIE's own quarterly adjustment-factor
   methodology (see the constant-gap finding in `mbie_notes.md`), not
   prioritized ahead of the margin work above.

**Long-term goal:** an additive forecast — current price + crude's
estimated contribution + margin's estimated contribution + known/announced
tax changes (looked up, not modeled, since these are deterministic) +
eventually currency — plus turning the current qualitative Strong/
Moderate/Weak tiers into real probability/confidence intervals. The
backtest error spread already on record (0.4–7.3%, varying with lag
length) is a practical starting point for that — not rigorous statistics,
but real, empirically observed error, which beats inventing a number.

**Stack question, explicitly undecided:** whether to keep building on
Azure/Fabric or move new work (starting with the margin analysis above) to
a GCP-based stack (BigQuery/DuckDB + Looker Studio) was raised and
deliberately left open rather than decided. Abandoning Azure mid-series
would also abandon the project's original stated goal (comparing the
GCP-familiar author's experience against Microsoft's stack) and a fair
amount of working, verified infrastructure. Current lean: keep the
oil-price work on Fabric as already built; if a new stack gets tried, do
it on the *next* new direction (margin analysis) rather than migrating
what already works.

**The always-on argument that used to sit here was wrong — corrected 11
Aug 2026.** This section previously claimed that Fabric *requires* capacity
to stay running for anyone to view a published Power BI report, and scored
that as a real point in GCP's favour. That is true only for a workspace
backed by an F capacity, which is how this project happened to be set up —
it is not a property of Power BI. Verified empirically:

- Report 1's semantic model and report were republished to **My Workspace**
  (shared capacity, not the F2) and shared via **Publish to web**.
- With `nzfuelcapacity` in state `Paused` for 70 minutes — well past the
  one-hour publish-to-web cache — the report rendered with data.
- Cost to serve it: zero. F2 is now only needed for the weekly `dbt run`.
- New public URL is on `app.powerbi.com`, not `app.fabric.microsoft.com`;
  the old Fabric-workspace embed code is dead and should be deleted from
  Settings → Manage embed codes. **It wasn't** — that deletion was left
  undone until 13 Aug 2026, and the live second public link it left behind
  caused real confusion; see "Two models named `nz_fuel`" below.

Two related facts worth keeping: **F2 never bought viewer-licensing
relief** — free viewers on capacity-backed workspaces start at F64 — and
publish-to-web requires **import** mode (DirectQuery and live connections
are unsupported), model and report in the **same** workspace, and no
report-level DAX measures.

**Still open:** the account is 46 days from the end of a Power BI Pro trial
(ends ~26 Sep 2026). Whether publish-to-web from My Workspace survives on a
Free licence is unresolved — Microsoft's docs point both ways (the
publish-to-web page lists My Workspace as needing only "a Microsoft Power
BI license", while the licence-comparison page says Free users cannot use
sharing features). Graph reports the assigned licence as
`POWER_BI_STANDARD` / `BI_AZURE_P0` with no Pro SKU in the tenant, so the
trial appears to be tracked inside Power BI rather than in Entra. Check the
public link the day after the trial ends; fall back to Pro (~NZ$24/mo) or
PDF if it breaks.
