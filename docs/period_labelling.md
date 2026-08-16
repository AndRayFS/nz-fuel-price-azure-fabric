# Period labelling — replacing one `period_type` with several axes

Answers `research/period_labelling_brief.md`. Written 15 Aug 2026, offline
against `research/data/panel_weekly.csv` (1,164 weeks × 2 fuels,
2004-04-23 → 2026-08-07). No warehouse queries; the Fabric capacity was
never started for this work.

Deliverables:

- `seeds/period_flags.csv` — proposed replacement seed, 2,328 rows.
- `research/build_period_flags.py` — the rule that generates it. Nothing in
  the seed is hand-drawn except two named boundary dates, both marked in the
  script.

`seeds/periods.csv` is untouched, as are `models/`, `docs/architecture.md`
and `docs/mbie_notes.md`.

---

## The short version

The single crisis/calm axis is not merely coarse, it **disagrees with the
data on four of its six periods**, and it discards more crude-shock weeks
than it keeps. Replacing it with independent axes recovers a pass-through
result the old flag cannot see at all: on Final data, both fuels pass cost
through roughly twice as fast in high-volatility weeks (joint p < 0.0001),
where the same test against the old `crisis` flag returns p = 0.905 for
diesel. The *direction* is robust across every specification tried; the
coefficient is not, and §7 says why.

Two of those axes exist because the ADL thread found things this document
originally got wrong: **`data_status`**, without which the pass-through
result is not merely weaker but *inverted* as to which fuel responds, and
**`crude_move_regime`**, because volatility is blind to a large smooth climb.

| what changed | old | new |
|---|---|---|
| axes | 1 (`period_type`) | 9 (across 15 columns) |
| weeks with a value | 200 of 1,164 | 1,164 of 1,164 |
| crude-shock weeks identified | 77 | 135 |
| …of which the old seed never labelled | — | 82 |
| provenance | hand-drawn | rule, re-runnable |

---

## 1. What the old labels get wrong

Every week was cross-tabulated against a volatility regime derived below.

| `period_id` | type | high-vol weeks | normal weeks |
|---|---|---:|---:|
| `01_covid_2020` | crisis | **14** | 0 |
| `02_calm_own_refinery` | calm | 3 | 86 |
| `03_ukraine_2022` | crisis | 9 | **18** |
| `04_tariff_2025` | crisis | **0** | **13** |
| `05_calm_import_era` | calm | 4 | 30 |
| `06_iranus_2026` | crisis | **23** | 0 |
| *(unlabelled)* | — | **82** | 882 |

Read down the column:

- **`04_tariff_2025` does not clear the volatility threshold — but it does
  satisfy the criterion it was originally labelled on.** Over its 13 weeks
  crude in NZD goes 128 → 116, a cumulative −9.8%; the largest 8-week move
  inside it is −19%, and its weekly volatility (sd of log changes 0.055) is
  ordinary. Not one of its weeks clears the shock threshold at any setting
  tested. **This does not make the old label wrong**, and an earlier version
  of this section overstated it as "not a crude event". The label came from
  within-period lag behaviour, not volatility, and on that measure it looks
  like the 2026 crisis rather than like calm — best lag 2 with r = 0.914
  (petrol) and 0.921 (diesel), against 0.883/0.894 for `06_iranus_2026`, while
  the adjacent `05_calm_import_era` sits at r ≈ 0.42 with its best lag pinned
  at the search cap. Replicated here; the numbers are the ADL thread's.
  So the volatility axis and the project's older lag axis genuinely disagree
  on this period, and neither overrules the other. Both are weak — 13 weeks,
  on levels, with differing lag caps — and the defensible conclusion is that
  **no single measure here is strong enough to found a crisis/calm split**,
  which is the argument for several axes rather than a verdict on 2025.
- **`03_ukraine_2022` runs 18 weeks too long.** The volatility episode is
  2022-02-18 → 2022-04-22, ten weeks. The label continues to 31 Aug 2022,
  which loads two-thirds of a "crisis" period with ordinary weeks.
- **`02` and `05`, the two "calm" periods, contain 7 high-volatility weeks**
  between them — both are boundary artifacts, `02` ending on the first week
  of the Ukraine episode and `05` running three weeks into the 2026 one.
- **`01` and `06` are drawn well** — 14/14 and 23/23. The hand-drawn labels
  are not uniformly bad; they are unreliable, which is worse for a
  comparison than being uniformly bad.
- **82 unlabelled weeks are crude shocks**, i.e. 61% of all shock weeks in
  the file were being thrown away. Six entire episodes have no label at all
  (below).

And the confound the brief names is real and unfixable by moving
boundaries: in the week of 2022-03-18, `period_type` = `crisis` is
simultaneously carrying a crude shock, a −21.43 c/L excise cut, a retail
data-source change 11 weeks old, and a refinery closure 13 days away. In
`seeds/period_flags.csv` those are four columns.

---

## 2. The crude volatility regime — the one axis that had to be derived

### Measure

Weekly log change of `dubai_crude_nzd`, then a **centred** 9-week rolling
standard deviation.

- Log changes, not levels or differences, because `importer_margin` levels
  have tripled since 2004 and crude ranges 29–267 NZD/bbl; any threshold on
  an absolute quantity measures the era, not the week.
- NZD, not USD. FX accounts for 9.7% of the variance of NZD crude changes
  (var 0.00020 against 0.00202), so USD crude is close but not identical.
  NZD is what feeds `importer_cost`.
- **Centred**, and this is a real constraint on reuse. Classifying history is
  a retrospective job, and a trailing window dates every episode about four
  weeks after it starts. Anything wanting these flags as a live indicator
  must re-derive them with a trailing window and will get later, and
  different, boundaries.

The rounding of both crude columns to whole dollars (`mbie_notes.md`) puts
roughly ±0.5 of noise into each level, but at weekly moves of 1–3 dollars the
sd of a 9-week window is dominated by real movement, and the threshold below
sits at three times the median.

### Rule

Enter an episode at sd ≥ 0.060 (the 92nd percentile of the full sample),
stay in it until sd < 0.045 (85th), discard runs shorter than 4 weeks. The
hysteresis exists so that one quiet week does not split an episode; the
minimum length turned out to be **inert** — every run the rule produces is
already ≥ 8 weeks — and is kept only as a guard.

Percentiles of the 9-week centred sd, for calibration: p25 0.023, p50 0.030,
p75 0.041, p90 0.055, p95 0.078, p99 0.156.

### What it finds — nine episodes, 135 weeks (11.6%)

| episode | span | weeks | peak sd | 8-week move, min…max | in old seed? |
|---|---|---:|---:|---|---|
| `2004_run_up` | 2004-11-19 → 2005-01-07 | 8 | 0.064 | −0.18 … −0.04 | no |
| `2008_gfc_crash` | 2008-08-29 → 2008-10-24 | 9 | 0.061 | −0.49 … −0.12 | no |
| `2009_rebound` | 2008-12-12 → 2009-02-06 | 9 | 0.077 | −0.42 … +0.19 | no |
| `2015_glut_onset` | 2014-12-26 → 2015-03-06 | 11 | 0.102 | −0.53 … +0.23 | no |
| `2016_glut_trough` | 2015-10-16 → 2016-04-29 | 29 | 0.104 | −0.50 … +0.36 | no |
| `2016_opec_cuts` | 2016-09-09 → 2016-12-02 | 13 | 0.065 | −0.02 … +0.14 | no |
| `2020_covid_crash` | 2020-02-14 → 2020-06-19 | 19 | 0.207 | −1.04 … +0.78 | partly |
| `2022_ukraine` | 2022-02-18 → 2022-04-22 | 10 | 0.083 | +0.08 … +0.37 | partly |
| `2026_iran_us` | 2026-02-06 → 2026-08-07 | 27 | 0.185 | −0.43 … +0.91 | partly |

Six episodes — 79 weeks — were entirely absent from the old labelling, and
71 of those weeks are the three largest crude events of the sample's first
eighteen years: the 2008–09 crisis, the 2014–16 glut, and the 2016 OPEC
cuts.

### Why there is no episode-level `direction` column

The obvious next column is up/down. It cannot be written honestly at episode
level: **five of the nine episodes contain both a stronger than +15% and a
stronger than −15% 8-week move.** `2020_covid_crash` spans −1.04 to +0.78 —
a 65% collapse and a doubling, inside one episode. Any single direction
label is false for part of five of nine.

So direction is published per week and continuous, as `crude_move_8w`
(8-week log change). Sign it, threshold it, or interact with it directly;
the choice belongs to the model, not to the seed.

### Magnitude is a separate axis, because volatility is blind to a smooth climb

Added 16 Aug 2026 after the ADL thread pointed out the gap. The volatility
measure scores *jaggedness*, and a large move made in small steady steps
scores low. The clearest case: **Nov 2021 → May 2022 took crude 114 → 170
NZD/bbl, +49% in 30 weeks, at a weekly sd of 5.3%** — two thirds of those
weeks are `normal`. Calling a stretch that moves crude half again "ordinary"
is defensible for a volatility axis and indefensible as a description of the
period.

`crude_move_regime` (`large_up` / `large_down` / `normal`) fixes this on a
**26-week** window at |log move| ≥ 0.35, just under the p90 of 0.405. The
window length is not a free choice: that climb averages 1.3% a week, so an
8-week window sees only ~+11% of it and a 13-week window ~+59% at its peak
but little either side. Half a year is what a drift that slow requires.

The two axes are not substitutes — of the 168 weeks flagged `large_up` or
`large_down`, **100 are `normal` on volatility**, including the tail of the
2008 crash, the 2008 run-up, the 2020 recovery and mid-2022. Volatility says
how rough the ride was; magnitude says how far it went.

---

## 3. Policy steps — 34, not 6

Taken straight from week-over-week `taxes` per fuel. The threshold matters:
before 2010 `taxes` is quantised to 0.1 c/L and diesel's value rounds back
and forth between 0.3 and 0.4 for years, so a 0.1 c/L threshold reports 257
"steps" of which 223 are that rounding. At **0.2 c/L** the count is 34, and
every one is a real excise, RUC or regional-fuel-tax change.

The brief's table listed 6. The other 28 are the annual excise indexation
steps — 2005-04-08 (+5.10), 2007-07-06 (+1.50), 2008-07-04 (+2.10),
2009-10 (+0.90, +2.10), 2012-08 (+1.43, +0.57), 2013-07-05 (+3.00),
2014-07 (+2.57, +0.43), 2018-10-05 (+3.00), 2019-07-05 (+3.80),
2020-07 (+2.51, +1.00), among others. They are smaller than the 2022 cut but
they are not small: eight of the 24 steps outside the brief's table exceed
2 c/L, against a typical weekly move of 2.02 c/L in the price itself. A tax
dummy that covers only 2022–2024 leaves 24 real steps sitting inside
"ordinary" weeks.

Diesel has just 2 steps in 22 years — the 2018 Auckland regional fuel tax and
its 2024 removal — confirming that diesel and petrol are not comparable on
this axis at all.

Two oddities recorded, not resolved: petrol shows **decreases** of −0.23 and
−0.57 c/L on 2017-06-30 and 2017-07-07, which no policy change explains; and
both fuels move by exactly +0.482390 on 2018-06-29 and +2.894339 on
2018-07-06, the Auckland regional tax entering the national weighted
average across two weeks.

`tax_step_window` covers the step week and the one after, because the steps
demonstrably smear across two weeks. 34 steps produce 57 flagged rows — 50
petrol weeks and 7 diesel — fewer than 68 because steps in consecutive weeks
share a window.

---

## 4. Data regimes

### The 2010 break is sharper than the brief describes, and one of its two claimed fingerprints does not survive

Confirmed: the identity `adjusted_retail − taxes − gst − ets −
importer_cost − importer_margin` is **exactly 0.000 in every row from
2010-01-08**, and fails in 589 of the 596 rows before it (max |residual|
13.8 c/L, diesel, 2008-05-16). The last non-reconciling week is
**2010-01-01** — a sharper boundary than "before 2010".

**A second, independent fingerprint lands on the same date.** `board_price`
is quantised to 0.1 c/L in every row from 2004 through 2009 — zero values
finer than 0.1 in six years — and the first finer value, for both fuels, is
**2010-01-08**. Same week. Two unrelated properties of the file change
together, which is what a genuine source or systems change looks like.

**The GST fingerprint does not reproduce.** The brief reports the implied GST
rate wobbling 11.5–13.5% before 2010 instead of sitting at 12.5%. On the
natural base it does not wobble at all:

| implied rate, pre-Oct 2010 | min | p5 | p95 | max |
|---|---|---|---|---|
| `gst / (adjusted_retail − gst)` | 12.43 | 12.45 | 12.55 | **12.58** |
| `gst / (price_excl_tax + taxes)` | 12.43 | 12.45 | 12.57 | 12.83 |
| `gst / (cost + margin + taxes + ets)` | 11.26 | 11.92 | 13.06 | **14.09** |

A clean 12.5%, ± rounding. The 11–14% spread appears only on the third
definition, whose denominator is rebuilt from the very components that fail
to reconcile — so the wobble is a *restatement of the identity break*, not a
second symptom of it. The conclusion (exclude pre-2010 from identity work) is
unaffected; the count of independent evidence for it changes from two to two
different ones.

For completeness, GST itself steps 12.5% → exactly 15.000% at 2010-10-01 and
never moves again, so the rate change is a policy step, cleanly separable
from the January data break nine months earlier.

**Scope of the exclusion matters.** The break is in the *decomposition*, not
in the prices. `board_price − taxes − gst − ets` uses none of the broken
components and is usable back to 2004; anything touching `importer_cost` or
`importer_margin` is not. `identity_holds` is a separate column from
`data_regime` for exactly this reason.

### 1 Jan 2022 — retail source, Envisory → Datamine

Both fingerprints from `mbie_notes.md` reproduce exactly.

- Weeks with `board_price` unchanged from the previous week: 4–28 per year
  per fuel through 2021, and the last one is **2021-12-24** for both fuels.
  Zero in the 240 weeks since.
- Diesel's precision: 26 of 52 values finer than 0.1 c/L in 2021, **52 of 52**
  from 2022. Petrol was already at 52/52 from 2019, so the change is
  diesel-only — the same shape as a fuel-specific behavioural effect, which
  is why it needs its own column.

### 31 Mar 2022 — Marsden Point

Kept as `supply_chain` (`domestic_refinery` / `import_only`), boundary
2022-04-01. This is an external fact, not a rule output, and it is
**inseparable in this data** from both the Datamine change 13 weeks earlier
and the Ukraine episode running through it. A residual test over the eleven
weeks around it returns +0.53 mean z for diesel and −0.53 for petrol — equal
and opposite, which is the signature of the confound, not of a mechanism.
The column exists so a model can *exclude* the boundary, not so anyone can
estimate its effect.

---

## 5. Candidate events tested and discarded

Method: regress Δ(`board_price` − taxes − gst − ets) on five lags of
Δ`importer_cost`, per fuel over the full sample, and read the standardised
residuals in each event window. That residual is the part of the price move
that cost does not explain, which is where a domestic supply or demand event
would have to show up. Reference scale: a 9-week rolling mean of those
z-scores has sd 0.27 (petrol) / 0.32 (diesel), 5th–95th percentile
−0.44…+0.42.

| candidate | window | petrol mean z | diesel mean z | verdict |
|---|---|---:|---:|---|
| Auckland pipeline rupture | 2017-09-08 → 11-03 | **+0.00** | **+0.09** | **invisible — discarded** |
| COVID L4 lockdown | 2020-03-20 → 05-29 | +0.56 | +0.23 | suggestive, hopelessly confounded |
| Aug 2021 Auckland L4 | 2021-08-13 → 10-29 | +0.28 | +0.25 | inside normal range — discarded |
| Marsden Point closure | 2022-03-18 → 05-27 | −0.54 | +0.53 | confounded, opposite by fuel |
| 2025 tariff period | 2025-04-02 → 06-30 | −0.11 | −0.17 | nothing there |

**The 2017 pipeline rupture is not in this data.** The brief called it the
cleanest possible example of why "crisis" needs to distinguish cause; it is
instead a clean example of an event that a weekly national average cannot
see. Petrol's mean residual over the nine weeks is 0.00 — not small,
literally zero to two decimals. Looking directly at the weeks, `board_price`
sat unchanged at 204.9 c/L for three consecutive weeks while crude rose
74 → 77 NZD, which is unremarkable for 2017, when 23 petrol weeks that year
were unchanged. The rupture's effect was concentrated in jet fuel and in
Auckland forecourt availability, neither of which this file measures. No
column for it.

**No demand-shock column either.** The mechanism that separates a demand
shock from a supply shock is that quantity moves the opposite way, and there
is **no quantity series in this panel**. What can be measured — a residual —
gives +0.56 for petrol in 2020 (about 2 sd, so notable) and nothing for
diesel or for 2021, and the 2020 window sits inside the largest crude
collapse in the sample, so the residual is at least as likely to be
asymmetric pass-through during a fall as a demand effect. Asserting
`event_kind = demand` on that evidence is exactly the move that has killed
five findings in this project already. It is left out.

**The ETS auction calendar survives, and is the one candidate that passed.**
Weekly |Δ`ets`| in the final month of each quarter (March, June, September,
December), against all other months:

| era | quarter-final month | other months | ratio | Mann-Whitney p | permutation p |
|---|---|---|---|---|---|
| 2021+ (auctions running) | 0.527 (n=96) | 0.341 (n=197) | **1.54** | 0.004 | 0.004 |
| 2010-07 → 2020 (no auctions) | 0.016 (n=183) | 0.028 (n=365) | 0.55 | 0.37 | 0.86 |

ETS moves 54% larger in auction months, and the placebo on the decade before
auctions existed shows nothing — in fact leans the other way. This is derived
purely from the calendar, with no external auction dates assumed, and it
supports the brief's framing that `ets` is a market factor. Kept as
`ets_auction_quarter`.

---

## 6. The 964 unlabelled weeks

**The question dissolves under the new schema, and that is the
recommendation.** Every axis in `period_flags.csv` has a defined value for
all 1,164 weeks. `crude_vol_regime = normal` is a measurement — the 9-week
volatility was below the 92nd percentile — not an absence of one. There is
no residual category and nothing to drop.

This matters more than it did when the brief was written, because "non-crisis"
has since become a sample that gets *estimated on*, not merely compared
against (§7). Under the old seed that sample was whatever was left after six
hand-drawn periods; under the flags it is 1,029 weeks with a stated
criterion, of which 757 are at 2010+ against 197 in the import era alone. The
normal-regime estimate is the stable one, so it is worth giving it the larger
sample rather than confining it to the import era out of habit.

Concretely: any comparison against the old seed silently discarded 83% of the
sample *and* 61% of the crude-shock weeks in it. Under the new flags a
crisis/calm contrast is `high` (135 weeks) against `normal` (1,029), on the
full panel, subset by `data_regime` or `identity_holds` as the model
requires.

---

## 7. Does the new flag actually do anything?

The point of the exercise is step 7 of the ADL plan: interacting the shape
parameters with a regime flag. Worth checking the flag is not merely tidier.

Test: Δ(`board_price` − taxes − gst − ets) on Δ`importer_cost` at lags 0–4,
fully interacted with the regime dummy, HAC (Newey-West, 4 lags) standard
errors. Sample 2010+ so the identity break is out.

| fuel | flag | sample | flagged n | Δβ₀ | p(Δβ₀) | joint F on all 5 | mean lag |
|---|---|---|---:|---:|---:|---:|---|
| Diesel | **`crude_vol_regime`** | Final, pre-2026 | 82 | +0.224 | 0.001 | **<0.0001** | 1.64 → **0.68** wk |
| Petrol | **`crude_vol_regime`** | Final, pre-2026 | 82 | +0.275 | 0.001 | **<0.0001** | 1.44 → **0.48** wk |
| Diesel | `crude_vol_regime` | Final, incl. 2026 | 90 | +0.066 | 0.380 | **<0.0001** | 1.64 → 1.07 wk |
| Petrol | `crude_vol_regime` | Final, incl. 2026 | 90 | +0.043 | 0.668 | **<0.0001** | 1.44 → 0.86 wk |
| Diesel | `crude_vol_regime` | 2010+, all weeks | 109 | +0.104 | 0.016 | 0.007 | 1.64 → 1.17 wk |
| Diesel | old `crisis` | 2010+, all weeks | 77 | +0.006 | 0.910 | 0.905 | 1.40 → 1.27 wk |
| Petrol | `crude_vol_regime` | 2010+, all weeks | 109 | +0.042 | 0.554 | 0.298 | 1.44 → 1.23 wk |
| Petrol | old `crisis` | 2010+, all weeks | 77 | −0.092 | 0.122 | 0.237 | 1.27 → 1.38 wk |

**Quote the direction and the joint test, not Δβ₀.** Added 16 Aug 2026 after
the ADL thread could only half-replicate this — they got the joint result and
the halved mean lag but insignificant individual contrasts. Reconciled, and
they were right to flag it. The cause is not the ECM term their specification
carries (adding it moves Δβ₀ by 0.003) but the **eight Final weeks of Feb–Mar
2026**, which take petrol's Δβ₀ from +0.275 to +0.043 and diesel's from
+0.224 to +0.066. `cost_backfilled` accounts for only two of the eight —
excluding them recovers petrol to +0.109, still not to +0.275.

So six weeks of genuinely Final, non-backfilled data move the point estimate
by a factor of three. Those six are the most extreme in the sample
(`crude_vol_9w` 0.066–0.177, against an entry threshold of 0.060), so this may
be real behaviour at extreme intensity rather than contamination — but a
coefficient that six observations can triple is not a coefficient worth
quoting. What survives every specification tried — both fuels, both cutoffs,
with and without an ECM term — is the **joint** test at p < 0.0001 and the
direction: the mean lag roughly halves, landing between 0.44 and 1.07 weeks
depending on sample.

Read carefully:

- **Both fuels pass cost through faster in high-volatility weeks, on Final
  data.** Mean lag roughly halved, joint test below 0.0001 in every
  specification. The old `crisis` flag cannot see this over 2010+ at all
  (p = 0.905 for diesel) — it is diluted by the ordinary weeks in `03` and
  `04` and blind to the 82 unlabelled shock weeks.
- **Petrol's null was itself an artifact of the unfinalised weeks.** On the
  full 2010+ sample petrol shows nothing (p = 0.554, joint 0.298); dropping
  the 19 Provisional weeks turns it into the *stronger* of the two fuels
  (p = 0.001, joint < 0.0001). The earlier version of this section read that
  null as a possible fuel asymmetry. It was contamination, and the direction
  of the error is worth noting — bad weeks did not merely add noise, they
  reversed which fuel appeared to respond.
- **`data_status = 'final'` is necessary but not sufficient.** It is what
  rescues the joint test and un-inverts the fuels. It does not stabilise the
  individual coefficients, because the Final Feb–Mar 2026 weeks remain
  (above). For a coefficient, cut at 2025-12-31 as well and say so.
- **Neither flag separates pass-through *completeness*.** Σβ over five lags
  is 0.88–1.01 in every cell, with HAC standard errors of 0.05–0.10 — no
  difference anywhere near significance. What moves is speed, not the total.
- **Multiplicity:** four cells were tested here, two fuels × two flags. The
  diesel result at p = 0.007 survives a Bonferroni correction over those
  four; the import-era result is on an overlapping sample and is not
  independent evidence.

### The flag locates a known instability (added after the ADL thread asked)

The parallel thread found diesel's total pass-through climbing with lag
length on the import era — 0.83 at K=3 to 1.21 at K=12 — so the number was a
statement about the analyst's choice of K. Seasonality, error correction and
factor autocorrelation had each been tested and failed to explain it.
Reproduced here at 0.832 → 1.215, spread 0.383.

Four tests, in order of what they rule out:

**It is the 2026 episode, and not just any 27 weeks.** Dropping each of the
189 contiguous 27-week blocks of the import era in turn, and ranking by the
resulting spread: the block starting 2026-02-06 ranks **2nd of 189**
(0.143 against a baseline 0.390). The top five are all the same window
shifted by a week or two. Nothing else in the sample comes close. The
inverse is also informative — dropping 2025-10-24 → 2026-04-24, which
removes the run-up but keeps the collapse, *raises* the spread to 0.680.
Splitting the episode is worse than either keeping or dropping it whole.

**It is not leverage.** High-volatility weeks have 5× the factor variance
(sd of Δ`importer_cost` 14.9 against 3.0), so mechanical domination of OLS
was the obvious suspect. Weighting by inverse local crude variance, dropping
nothing, leaves the spread at 0.380 against OLS's 0.390. Downweighting the
volatile weeks does not stabilise the estimate.

**It is not degrees of freedom.** With 27 high weeks and 13 coefficients at
K=12 the interacted fit is nearly saturated, so the climb could have been
overfitting. It is not: on 2010+ there are **109** high weeks — 8.4
observations per parameter at K=12 — and the climb survives almost unchanged.

**But it is not the volatility regime either. Corrected, 16 Aug 2026.** An
earlier version of this section concluded from the three tests above that the
instability "lives entirely in the high-volatility weeks", and recommended
estimating the crisis regime on 2010+ for the larger sample. That conclusion
was wrong, and the error is instructive: enlarging the sample to 2010+ left
2026 *in* it, so the surviving climb was evidence about 2026, not about
high-volatility weeks in general. The test not run was the obvious one —
remove 2026 and see whether anything is left.

| 2010+ sample | high weeks | normal spread K=3…12 | **high spread K=3…12** |
|---|---:|---:|---:|
| all weeks | 109 | 0.148 | **0.431** |
| 2026 episode dropped | 82 | 0.148 | **0.154** |
| all of 2026 dropped | 82 | 0.142 | **0.154** |
| only Provisional (Apr 2026+) dropped | 90 | 0.148 | **0.106** |

With 82 high-volatility weeks from 2010 to 2025 — all of them Final data —
the high regime is as stable as the normal one (0.154 against 0.148). The
climb is not a property of crude shocks. It is a property of 2026, and
narrows further: dropping just the **19 Provisional weeks** stabilises it
*more* than dropping the whole 27-week episode, while leaving 90 high weeks
in the sample. The fierce Final crisis weeks of Feb–Mar 2026 are not the
problem; the unfinalised ones are.

This matches what the ADL thread found independently and from the other
direction, and what MBIE's own pages say (below). Credit for the diagnosis is
theirs; this section is the confirmation on the volatility axis.

**So the honest statement is narrower than either "diesel is not identified"
or "the crisis is not identified": diesel pass-through is stable and complete
on Final data in both regimes, and the instability is an artifact of weeks
MBIE has not finalised.** The high regime is estimable after all — on
2010–2025.

Why the data status does this, from MBIE's pages rather than inference:
everything from **1 Apr 2026** is Provisional pending the Stats NZ
June-quarter CPI, and separately MBIE **suspended publication of
`Importer cost` and `Importer margin` from 18 Mar to 1 Jul 2026** over
conflict-driven volatility and backfilled those weeks afterwards. Only those
two series were paused — retail, board, tax, ETS and FX ran normally — and
they are exactly the two the pass-through regression uses as its factor. Both
facts are now axes in the seed (`data_status`, `cost_backfilled`) so this is
expressible rather than implicit.

The volatility episode boundaries themselves do **not** depend on any of
this: `crude_vol_9w` is computed on `dubai_crude_nzd`, not on
`importer_cost`. Crude was revised in the affected window too, though, in
whole-dollar steps, so the 2026 boundaries should be re-derived once those
weeks finalise.

Practical consequence for step 7: filter on `data_status = 'final'` before
anything else, and estimate the crisis regime on **2010–2025**, where there
are 82 high weeks of finalised data.

### Threshold sensitivity

Δβ₀ for diesel, across 18 configurations of window span, entry threshold,
stay threshold and minimum length:

| span | enter | weeks flagged | episodes | diesel Δβ₀ | p (joint) |
|---:|---:|---:|---:|---:|---:|
| 7 | 0.05 | 186 | 18 | +0.099 | 0.195 |
| 7 | 0.06 | 130 | 10 | +0.110 | 0.008 |
| 7 | 0.07 | 100 | 7 | +0.102 | 0.013 |
| 9 | 0.05 | 189 | 16 | +0.100 | 0.105 |
| **9** | **0.06** | **135** | **9** | **+0.104** | **0.007** |
| 9 | 0.07 | 105 | 6 | +0.101 | 0.014 |
| 13 | 0.05 | 204 | 14 | +0.099 | 0.108 |
| 13 | 0.06 | 124 | 6 | +0.098 | 0.016 |
| 13 | 0.07 | 111 | 5 | +0.094 | 0.065 |

The coefficient is +0.094 to +0.114 everywhere — the estimate does not depend
on the threshold. Significance does: at entry 0.05 it fades (p 0.10–0.20),
because that setting admits ~55 additional ordinary weeks and dilutes the
contrast. That is itself informative — the speed-up belongs to genuinely
extreme volatility, not to mildly choppy weeks. Varying the stay threshold
(0.040/0.045/0.050) moves Δβ₀ between +0.098 and +0.114; varying minimum
length changes nothing at all, since every run already exceeds every value
tested.

---

## 8. Schema

`seeds/period_flags.csv`, one row per (week, fuel), 2,328 rows. Join key
`week_date` + `fuel`.

| column | type | measured or given | meaning |
|---|---|---|---|
| `week_date` | date | key | MBIE's Friday stamp |
| `fuel` | text | key | `Regular Petrol` / `Diesel` |
| `crude_vol_regime` | `high` / `normal` | **measured** | hysteresis episode over the 9-week centred sd |
| `crude_vol_9w` | float | **measured** | the sd itself — cut it differently if you prefer |
| `crude_vol_window_full` | bool | **measured** | false for the first and last 4 weeks, where the centred window is truncated |
| `crude_episode_id` | text / empty | **measured boundaries**, narrative name | see the warning below |
| `crude_move_8w` | float | **measured** | 8-week log change of `dubai_crude_nzd`; direction lives here |
| `crude_move_26w` | float | **measured** | 26-week log change — magnitude, independent of jaggedness |
| `crude_move_regime` | `large_up` / `large_down` / `normal` | **measured** | \|`crude_move_26w`\| ≥ 0.35; 100 of its 168 weeks are `normal` on volatility |
| `tax_step_cpl` | float | **measured** | Δ`taxes` for that fuel, zeroed below 0.2 c/L |
| `tax_step_window` | bool | **measured** | step week and the one after |
| `data_regime` | `pre2010_unreconciled` / `envisory` / `datamine` | measured + given | boundaries 2010-01-08 (rule) and 2022-01-01 (MBIE methodology) |
| `data_status` | `final` / `provisional` | given | Provisional from 2026-04-01, pending the Stats NZ June-quarter CPI. **Filter on this first** — §7 |
| `cost_backfilled` | bool | given | 2026-03-18 … 2026-07-01, where MBIE suspended and later backfilled `importer_cost` and `importer_margin` only |
| `identity_holds` | bool | **measured** | whether the decomposition closes to 0.000 |
| `supply_chain` | `domestic_refinery` / `import_only` | given | boundary 2022-04-01, Marsden Point |
| `ets_auction_quarter` | bool | given calendar, **tested** | final month of a quarter, from 2021 |

**`crude_episode_id` names are labels, not claims.** The boundaries are rule
output; `2022_ukraine` and `2016_opec_cuts` are shorthand attached for
reading charts. Nothing downstream should branch on the string, and no
causal statement should rest on it. This is the one place in the seed where
narrative is present at all, and it is confined to a column that carries no
weight.

### Deliberate omissions

- **No `event_kind` / demand-vs-supply column.** Not identifiable without a
  quantity series (§5).
- **No `domestic_supply_event` column.** The only candidate testable in this
  file is invisible in it (§5); a column that is false in all 2,328 rows adds
  nothing but the appearance of coverage.
- **No episode-level direction.** False for part of five of nine episodes
  (§2); `crude_move_8w` carries it per week instead.
- **No `crisis` column under any name.** The word bundles cause, direction,
  magnitude and volatility, which is the failure being fixed.

---

## 9. How to use it, and what to watch

```sql
-- the intended step-7 contrast
where data_status = 'final'         -- FIRST: unfinalised weeks destabilise (§7)
  and identity_holds                -- decomposition trustworthy
  and not tax_step_window           -- no smeared policy step
-- then interact the ADL lags with (crude_vol_regime = 'high')
```

`data_regime = 'datamine'` narrows to one retail source, but on Final data it
leaves only **18** high-volatility weeks against **90** for `identity_holds`
(2010+) — prefer the wider window plus a `data_regime` dummy unless the source
change is itself the question.

Cautions:

1. **The volatility window is centred.** These flags classify history. Do not
   feed them to anything that must run in real time without re-deriving them
   on a trailing window.
2. **`crude_vol_window_full = false`** on 2004-04-23 … 2004-05-14 and
   2026-07-17 … 2026-08-07. The 2026 tail matters — the current episode is
   open, and its last four weeks are classified on a truncated window.
   Re-running `build_period_flags.py` after new weeks arrive will revise
   them, which is correct behaviour and not a bug.
3. **`seeds/` is a dbt seed path.** Dropping this file there means the next
   `dbt seed` loads it into the warehouse whether or not it has a
   `_seeds__models.yml` entry. Merging it properly means adding that entry
   (with `accepted_values` tests on the three categorical columns, which is
   how `periods` is already tested) — deliberately not done here, since the
   brief reserves the merge decision.
4. **Regenerate, don't edit.** `python research/build_period_flags.py`. The
   file is derived; a hand edit will be silently overwritten.

## 10. What was not settled

- **Petrol's null result.** Whether petrol genuinely does not speed up in
  shocks, or whether the 2022 diesel-only precision change is manufacturing
  the diesel result, cannot be told apart here. A test on 2010–2021 alone
  would separate them and was not run.
- **The 2017-06-30 / 07-07 petrol tax decreases** (−0.23, −0.57 c/L) have no
  identified cause.
- **The 2020 COVID residual** (+0.56 z for petrol) is real in the sense that
  it is about 2 sd, and uninterpretable in the sense that it sits inside the
  largest crude collapse in the sample. Separating a demand effect from
  asymmetric pass-through during a fall needs the ADL work, not a flag.
- **Whether `crude_vol_regime` should be three-way.** A `calm` tier (say
  `crude_vol_9w` below the 25th percentile, 0.023) is one line of SQL away
  and was not tested, because the step-7 contrast is binary.

- **"Pass-through exceeds 100% at extreme intensity", n = 8.** The eight Final
  Feb–Mar 2026 weeks are the most extreme in the sample (`crude_vol_9w`
  0.066–0.177 against a 0.060 threshold) and they are what moves both this
  document's Δβ₀ and the ADL thread's diesel total from straddling one to
  entirely above one. The hypothesis that this is real behaviour rather than
  contamination is worth naming, and it is **not settled**.

  One attempt to settle it, recorded because it failed informatively. If
  intensity genuinely drives pass-through, a gradient fitted on the 82 Final
  pre-2026 high weeks should predict what the eight show. Interacting the cost
  lags with continuous `crude_vol_9w` gives a significant interaction —
  petrol p < 0.0001, diesel p = 0.0039 — but the two fuels move in **opposite
  directions**: extrapolated to the intensity of the eight weeks, petrol's
  total *falls* to 0.87 and diesel's *rises* to 1.10. And the underlying data
  show no gradient at all. Total pass-through by intensity tercile among those
  same pre-2026 high weeks:

  | tercile | mean `crude_vol_9w` | n | Σβ petrol | Σβ diesel |
  |---|---:|---:|---:|---:|
  | low | 0.053 | 28 | 0.715 | 0.750 |
  | mid | 0.074 | 27 | 1.568 | 1.182 |
  | high | 0.126 | 27 | 0.620 | 0.829 |

  Non-monotone in both fuels, and the mid tercile is the outlier rather than
  the high one. With 27 weeks against 6 parameters these bins are thin, so the
  wildness is unsurprising — but that is the point: **there is no stable
  intensity gradient here to extrapolate from**, and the significant continuous
  interaction is fitting influential weeks, not a trend. The hypothesis
  therefore rests on the eight weeks alone and cannot be supported from the
  rest of the sample. It needs the 2026 weeks to finalise, not more modelling.
