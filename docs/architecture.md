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

## Roadmap — where this goes next, in priority order

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
2. **EIA Brent (daily crude benchmark) as a new source.** Solves two
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
3. **Distributed lag model (ADL).** The deeper, correct fix for the
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
4. **Stats NZ** as a candidate secondary source — mainly useful as an
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
  Settings → Manage embed codes.

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
