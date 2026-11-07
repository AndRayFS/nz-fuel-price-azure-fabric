# Model plateau — panel review, 7 Nov 2026

Three independent reviewers: an econometrician, a NZ fuel-market
practitioner and an operational forecaster. Each saw only
`research/model_plateau_brief.md`, and none saw the repo or the other reviews.
Their raw reviews are in the appendix. After the reviews came in, the gaps
they raised were checked against the repo (section 3). Nothing here is a
result yet. It is a plan with one pre-registered test (section 5).

## 1. Where all three agree

| # | Finding | Econ | Market | Forecaster |
|---|---|---|---|---|
| 1 | Stop searching point-forecast specifications on the same weekly data; freeze `adl_ecm` as the point model | ✔ | ✔ | ✔ |
| 2 | The evaluation cannot tell effects of this size from noise: no CIs, verdicts on n = 9, "no worse than" rules on < 30 weeks | ✔ | ✔ | ✔ |
| 3 | The evaluation does not match production: centred regime label, revised (post-23 Sep) data in 2026 tests, fuels pooled, Premium 95 left out | ✔ | ✔ | ✔ |
| 4 | Try 7 is the only large gain but post-hoc: freeze it and score it out of sample before deciding on a licensed pump feed | ✔ | ✔ | ✔ |
| 5 | The metric does not match the product: point MAE vs confidence tiers. **Premise partly wrong, see 3.1** | ✔ | ✔ | ✔ |

## 2. Where they differ

- **Try 1, the nowcast.**
  - Econometrician: it is the only PASS on a long sample and was vetoed on
    noise. Re-judge it on all weeks, then run it in shadow.
  - Forecaster: the PASS is probably inflated by the centred label. Keep it
    only as a fixed 50/50 combination, switched off when trailing volatility
    or the Yahoo–FRED basis is high.
  - Market practitioner: Brent is the wrong driver. NZ imports refined
    product, so the input should be product prices × FX.
- **Reading 2, "better cost inputs make it worse".**
  - Econometrician: two errors cancel, in one episode.
  - Forecaster: in a crisis, retailers price off pump-side information.
  - Market practitioner: retailers recovering margin, plus the futures basis
    in backwardation. That is a different failure from the one with spot and
    ComCom inputs.
- **Margin.** The market practitioner proposes a causal margin-gap term
  (trailing 13 weeks). The others say to stop changing the specification.
  Unresolved: this is the one specification change aimed at a mechanism
  that has not been tested yet.
- **Try 7's gain.** The econometrician says it is partly mechanical overlap.
  The market practitioner says h=1 is mostly decided before the run. Same
  fact, two readings; it is confirmed in 3.2.

## 3. Checked against the repo after the reviews

| # | Gap raised | Answer | Source |
|---|---|---|---|
| 3.1 | What the "confidence tiers" are | **There are none in Report 1** (owner, 7 Nov). The `resolved_r` tiers came from the first version of the project and were fully removed by 8 Sep. Only text remains, in `docs/architecture.md:1778`, CLAUDE.md and three other docs. Report 1 shows uncertainty two ways. On Now, a **band**: the middle half (25–75%) of past misses at the same horizon, in weeks of the newest week's crude-volatility regime, three fuels pooled. On Track record, the history of misses. So the reviewers' "calibrate the tiers" becomes "check the band": does it hold half of the outcomes? The newest week's regime comes from a centred window cut short at the edge (`crude_vol_window_full = False`), while the past misses are labelled with full windows, i.e. with hindsight. **The brief took "confidence tiers" from stale docs, and that error reached all three reviewers** | `pipeline/phone_page.py:92`, `pipeline/build_period_flags.py:157,204` |
| 3.2 | Which days a week covers | Each week is stamped on its Friday and runs Monday–Sunday. At the Wednesday run, Monday, Tuesday and part of Wednesday of week t+1 (the h=1 target) have already happened. Try 7 sees 2 of the 7 days its target averages, so part of its gain is mechanical overlap | `docs/mbie_notes.md:240` |
| 3.3 | Real-time or revised data in backtests | Revised, knowingly: the backtest uses the current vintage. Vintages exist in the snapshot from 17 Jul 2026, so a pre-23-Sep rerun is possible, but only through the warehouse | `pipeline/backtest.py:41` |
| 3.4 | Did the bad Yahoo point (18 Sep) enter try 2 | Not checked. Its weight is one day in a weekly mean, under 1% of it | `docs/research.md:1854` |
| 3.5 | Was try 2's window chosen after seeing errors | No. It was set as a shipping condition on 19 Sep, before most of the scored weeks existed, and written into the script before running | `docs/research.md:1866` |
| 3.6 | Were try 7's weights fitted on the weeks they were scored on | No. They were fitted walk-forward, on earlier weeks only. The post-hoc part is choosing a combination after the primary method failed | `docs/research.md:2235` |
| 3.7 | 20–27% better than naive overall vs 45–63% in 2026 | Different samples, not a contradiction. It does say 2026 suited a cost-lag model unusually well (long one-way moves), so it is atypical even among crises | sections 4, 6 of the brief |
| 3.8 | Try 1's sample and its result over all weeks (econometrician) | **Missed in the first version of this section; raised by the owner.** Try 1 also won in crisis weeks: −9–15% over the six past episodes in the forecast sample, and −2.0% / −10.2% (h=1 / h=2) over the whole 2026 episode. Try 2's veto rests on the smallest available crisis sample, the backwardation window of 9 weeks per fuel, and it is the only negative one | `docs/research.md:1741`, `:1912` |

## 4. Recommended sequence (synthesis; the owner decides)

1. **Fix the scorecard before building any new model.**
   - Results per fuel, including 95.
   - Moving-block bootstrap CI on the MAE ratio.
   - The regime split is descriptive only.
   - A verdict counts only if its CI excludes 1.
   - Re-score tries 1, 2 and 4 under these rules (first test, section 5).
   - Offline, archive only.
2. **Decide what the product promises.** If the report is to say how sure it
   is, build intervals from walk-forward residuals, scaled by trailing crude
   volatility, which is known at forecast time. No new data needed. This
   depends on 3.1.
3. **Start try 7's out-of-sample clock now; it is tied to the calendar.**
   - Freeze the combination weights on the weeks to date.
   - Score them fortnightly as ComCom publishes, about 1 h each time.
   - After about 12 weeks, decide whether a licensed timely feed is worth
     seeking.
4. **Only then:** the product × FX cost driver, the margin-gap term and the
   switched-off-in-volatility nowcast, each under the new scorecard and
   with a rule written before running.

**Stop:**
- point-specification search against 2026;
- "no worse than" rules on n < 30;
- pooled-only results;
- the centred label for any choice of method.

## 5. First test — pre-registered (draft: owner approves before it runs)

- **Question.** Do the verdicts of tries 1, 2 and 4 survive a confidence
  interval?
- **Method.** Take the existing walk-forward outputs: production and variant,
  per week, per fuel (Diesel, Regular Petrol). Compute the MAE ratio
  variant / production. Moving-block bootstrap: block of 8 weeks, 2,000
  resamples, 90% CI. Horizons as in each original test.
- **Rule.** A verdict stands if the 90% CI excludes 1.00 in its reported
  direction. Otherwise it becomes "not detectable".
- **Predictions, written now.** Try 2 (n = 9 per fuel): not detectable.
  Try 1 at h=2–3: stands. Try 4: not detectable.
- **Amendment, written before the run (7 Nov).**
  - Block of 8 weeks only when the sample has at least 32 weeks; below that,
    2 weeks. With n = 9, eight-week blocks leave two distinct blocks, and the
    CI means nothing.
  - Try 1 is re-scored on archive 2026-11-05, which has more weeks than the
    8 Sep run, per fuel including 95.
  - All three tries are on that archive, the same one tries 2 and 4 used.
  - Seed 20261107.
- **Part 2, added after 3.8: the nowcast on every crisis week.** The six
  past episodes plus the whole 2026 episode, per fuel, h=1 and h=2, with
  the same bootstrap. The backwardation window is reported inside it as a
  sub-sample and decides nothing on its own.
  - **Rule:** "does not hurt in crisis weeks" if the upper end of the 90% CI
    of the MAE ratio is below 1.05.
  - **Prediction:** holds at h=2. At h=1 the CI is wide.
  - **Caveat:** the 2026 weeks are on revised data (3.3).
- **What it changes.**
  - If try 2's veto is not detectable, the nowcast goes back into step 4.
  - If it stands, the nowcast line closes.
  - If try 1 does not stand, the only PASS goes with it.
- **Cost.** About 2–3 h. Data: the published archive, no warehouse.

## 6. Result of the first test — 7 Nov 2026

`research/verdict_ci.py`, archive 2026-11-05. Before anything was read, each
try's own script reproduced production's `pred_adl_ecm` to 0.00005 c/L. Try 2
reproduced its original figures exactly. FRED could not be reached; its spot
column feeds nothing here and was stubbed, as the run states. The full table
is in `data/verdict_ci/verdict_ci.csv`. MAE change of the variant against
production, 90% CI.

| Verdict | Was | Now | Prediction |
|---|---|---|---|
| Try 1, nowcast, non-crisis (597 weeks) | PASS | **Stands** for every fuel including 95 and every horizon: h=1 −6 to −9% (CI as high as −2%); h=2–3 −12 to −14% | Stands at h=2–3: **met**, and at h=1 as well |
| Try 2, nowcast in the backwardation (8–9 weeks) | FAIL, the veto | **Not detectable**: pooled h=1 +13.5% [−11.8, +32.2], h=2 +7.4% [−20.2, +110.8] | Not detectable: **met** |
| Try 4, recency weighting | FAIL | Non-crisis: **stands** for diesel and pooled, +1.5% [+0.2, +3.0]; not detectable for petrol. Crisis: not detectable | Not detectable: **missed**. The loss in calm weeks is small and real |
| Part 2, nowcast on every crisis week (119 per fuel) | — | **Does not hurt; it helps.** Pooled h=1 −10% [−17, −3], h=2 −14% [−19, −10], h=3 −11% [−15, −8]. Every fuel, including 95, meets the rule | Holds at h=2, wide at h=1: **met, and better** |

Inside part 2, descriptive only:

| Sub-sample | Weeks | h=1 | h=2 |
|---|---|---|---|
| Before 2026 | 82 | −15% | −17% |
| 2026 | 37 | −3%, CI up to +9% | −10% |
| Backwardation | 8 | +8%, CI −14 to +36 | — |

**What it means.**

- **The only idea that passed was shelved on a verdict the data cannot
  support.** Over every week, the nowcast is better in calm and crisis
  weeks, for all three fuels, at every horizon.
- **The centred label is not what makes it look good.** It wins on both
  sides of the label, which answers the forecaster's objection.
- **2026 is where it is weakest.** At h=1 the result is inconclusive; at h=2
  it is still better. The backwardation mechanism (futures below physical)
  is plausible but cannot be measured on 8 weeks.
- **Recency weighting stays closed**, now with a CI behind it.
- **Caveats.**
  - The data is the current vintage (3.3).
  - The three Brent days are in hand at the real run, Thursday 09:07 NZ
    (`infra/logic-apps/trigger-weekly-load.json`). In NZ summer that is
    20:07 UTC, about 40 minutes after ICE settles, so a late Yahoo bar would
    leave two days.
  - The Yahoo endpoint is undocumented, and one point has already been wrong.
- **Proposed next step (owner's decision):** reopen the nowcast as a shadow
  run, with a rule written before the weeks it is tested on. Run it beside
  production for 12 weeks, per fuel, with a guard that falls back to
  production when the Yahoo bar is missing or diverges from a second source.

## 7. Later the same day — the shadow run dropped, and futures rolls

- **A shadow run cannot test what it was proposed for.** Scaled from try 1's
  CIs, 12 weeks give about ±25–28 points at h=1–2 against a 7–13% effect. A
  shadow run alone would need about 40 weeks at h=2 and about four years at
  h=1. The 12 came from a reviewer and was not derived.
- **Most of what it would check is in history.** Yahoo's daily `BZ=F` is the
  settlement of the calendar front contract, so the "Wednesday not closed
  yet" risk mostly goes. The live view switches contract 4–9 trading days
  before expiry, and the 18 Sep "wrong point" was that switch. In roll weeks
  the nowcast does better, and the roll is a real move in MBIE's cost: 0.73
  of a spot move. Two of the owner's questions led here: "how do you know
  the hourly history was corrected too?" (it was not), and "what does 'the
  day is still going' mean after settlement?". `docs/research.md`, 7 Nov
  2026.
- **Left for live:** what Yahoo returns at the run for a contract symbol, and
  whether it answers a GitHub runner. That is a probe of a week or two.
- **Proposed next step (owner's decision):**
  - research: done;
  - production: the front contract by symbol, a guard, the band recomputed
    from the nowcast's misses (test B), the probe, then the switch;
  - `adl_ecm` stays computed beside it.

---

# Appendix — raw reviews (compressed, wording kept)

## Reviewer: econometrician sceptic

### Diagnosis
- Evaluation can't detect effects of the size chased. No CIs / DM tests; h=2–3 errors overlap. Test 2 vetoed the only long-sample PASS (test 1) with n=9/fuel from one episode under a "no worse than" rule — near coin-flip under no true effect. Test 4 (+0.1–1.5%) is a tie, not a fail. Reading 1 → "not detectable", not "not helping".
- 2026 sample is used up. Seven tries, many variants (3 cost inputs, several windows/half-lives, 4 asymmetry attempts), mostly on the same ~38 weeks. Test 7's post-hoc −48% is the kind of number many paths on one sample produce.
- Production's good 2026 fit rests on two cancelling errors (sharper reading 2): expanding-window slope understates cost moves; pre-2026 pass-through overstates how far pump follows. Coherent but one episode; tests 2 and 3 not independent confirmations. Reading 3 holds, so reading 2 can't be generalised.
- Cost regressor measurement error + possible look-ahead: 23 Sep restatement back to 27 Feb; 25 Sep "pump against cost" week right after. If backtests use revised data, cost lags and ECM margin contain info not available at forecast time. Bad Yahoo point (18 Sep) inside test 2's window.
- Metric doesn't match product: tiers vs point MAE; pooling (diesel dominates 2026) vs per-fuel production; go/no-go split on centred label.

### Proposals, ranked
1. Fix the evaluation and freeze 2026. Primary: per-fuel MAE over all weeks; DM with HAC or block bootstrap; regime split descriptive only; prospective holdout from Nov 2026, models frozen. Falsify: bootstrap 90% CI for test 2's +13.5% — if it excludes 0 the veto stands. Pass rule: a test is decisive only if its CI excludes 0. 6–8 h.
2. Re-judge test 1 on all weeks, then shadow. Pass (per-fuel DM, 2013+): MAE ≤ −3% at h=2 and h=3 both fuels, one-sided p<0.10; crisis pooled over all nine episodes no worse >5%; then 12 shadow weeks inside the CI. Guard flagging Yahoo vs FRED divergence. 4–6 h + futures history.
3. Calibrate tiers instead of the point: residual-quantile bands scaled by trailing crude vol. Falsify: if unscaled 80% bands already cover 75–85% of past crisis weeks, skip. Pass: per-fuel coverage ±5 pp overall, ±10 pp crisis, better interval score than unscaled. 6–10 h.
4. Check data versions: rerun 2026 with pre-23-Sep cost if archived; if production MAE moves <3%, drop. 2–3 h.
5. Postpone licensed pump-data decision. Mon–Tue are part of the days MBIE averages for week t+1 → part of test 7's gain is mechanical. Fix weights on Feb–Jun, score Jul+ and 2027. Pass: ≥10% better at h=1 per fuel, OOS. 3 h.

### Stop doing
- Point-forecast spec search against 2026. Freeze adl_ecm.
- Post-hoc combinations as headlines; "no worse than" rules on <30 weeks.
- Pooling fuels; leaving out 95.
- Method switching on the centred label.

### Gaps
- Test 1 sample, n, result over all weeks.
- Real-time vs revised data in backtests.
- Which days MBIE averages into a week (sets test 7's overlap with its own target).
- Did the bad 18 Sep Yahoo point enter test 2.
- Were test 7's weights fitted on the scored weeks.
- Was test 2's Sep–Oct window chosen after seeing errors.
- "20–27% better than naive" vs 45–63% better in 2026.
- How many crisis weeks across nine episodes.

## Reviewer: NZ fuel market practitioner ([DK] = domain knowledge, not brief evidence)

### Diagnosis
- h=1 is mostly decided before the run. [DK] Majors' desks move boards once the accumulated cost gap reaches a few cents; others follow in 1–2 days. By Wednesday most of week t+1 is set. Evidence: try 7 −48% h=1 → −10% h=3; try 2 cost nowcast 3–4× better yet no h=1 gain. Signal: daily pump prices or leaders' board moves.
- In a crisis, retailers decide on margin. [DK] Price to replacement cost, recover margin squeezed on the way up, pull discounts when supply is tight. Evidence: diesel 25 Sep (cost −17.5, pump +21.1); crisis MAE 2.2–2.5× non-crisis. ECM anchored on a 104-week mean margin reacts too slowly. Try 6 doesn't contradict: weekly asymmetry tests have little power; the effect is in lumpy timing.
- Brent is the wrong driver. [DK] NZ imports refined product (no refinery since 2022), priced off Singapore gasoline/gasoil, in NZD. The 0.67–2.03 slope is crack spread + FX soaked into a crude coefficient. Try 3 partly contradicts: right slope, worst forecast — fixing the driver helps the cost nowcast, not crisis pump forecasts.
- Reading 2 conflates two failures. Futures +13.5% worse; spot/ComCom "no better". [DK] In backwardation front-month futures read below prompt physical cost — a basis problem, not proof better cost inputs hurt.
- Noise exceeds tested effects. n=9/fuel (try 2), 60 post-hoc calls (try 7). If backtests use today's vintage, the 23 Sep adjustment leaks into the 2026 margin/ECM term. Agrees with reading 3. Reading 1 holds for lag/weighting tweaks, but pump behaviour vs margin gap is untested.

### Proposals, ranked
| # | What / why | Expected | Cheapest falsifying test | Pass rule | Cost |
|---|---|---|---|---|---|
| 1 | Freeze try-7 combination weights now; score out of sample on ComCom as published. Decides whether to seek a licensed timely source; if it fails, stop h=1 work | h=1 −20–40% if real | 12-week shadow, scored fortnightly after the fact; no timely feed needed | ≥20% below production at h=1 per fuel, not worse at h=2 | 4 h + 1 h/fortnight; ComCom |
| 2 | Judge product by tier calibration and direction at h=2–3, not MAE; h=1 forecasts a week already partly over | Honest metric; may show current model good enough | Hit rate + Brier on existing backtest for up/flat/down (±2 c/L) | Each tier's stated confidence within ±10 pp of realised frequency, both regimes | 3 h; archive |
| 3 | Product × FX cost driver: Yahoo HO=F, RB=F as rough Singapore proxies × NZD/USD, cross-checked with a 2nd source | More stable slope; h=2–3 gains non-crisis | Regress MBIE cost change on Brent vs product×FX, by year | By-year slope range ≤0.4; cost-nowcast MAE −25% | 6 h; free |
| 4 | Causal margin-state term: gap = margin − trailing 13-week median; adjustment accelerates with gap. Trailing (not centred) volatility sets tier width only | Catches margin-recovery moves | One extra term in existing backtest | ≥3% better h=1,h=2 non-crisis, not worse crisis | 5 h; archive |

### Stop doing
- Spec variants on the same weekly data (lags, weighting, own lags, asymmetry): the limit is information, not form.
- Crisis-specific coefficients/claims from one episode.
- Brent futures as cost proxy; Yahoo as single source.
- Promoting post-hoc combinations without frozen OOS scoring.

### Gaps
- How MBIE builds the average [DK, uncertain]: retailers, board vs discounted, sampled days, regional weights.
- Real-time vintages vs today's revised data in backtests.
- Whether importer cost includes FX and freight, and with what lag.
- Exactly which days h=1 covers relative to the Wednesday run.
- Premium 95 results; per-fuel splits for tries 2 and 7.
- Whether 2026 was a supply disruption.

## Reviewer: operational forecaster

### Diagnosis
- Wrong objective. Product speaks in confidence tiers and bans point language (§1, §8), yet every test is scored on point MAE (§3). Try 1's win is ~0.1 c/L at h=1 (7% of 1.40) — too small for a reader to notice. Nothing shows the tiers are calibrated, and that is the product's real accuracy claim.
- Calm weeks sit at the information ceiling. Tries 4–5 fail on the full sample, not just 2026. The only large gain (try 7) is new data, not new specification. Supports reading 1.
- Leaky evaluation. Centred label depends on future crude volatility → "non-crisis" = weeks where crude did not jump after the origin, exactly where a futures nowcast does well → try 1's PASS probably inflated. 2026 tests appear to use revised cost (23 Sep adjustment back to 27 Feb), which also shifts the ECM margin.
- Reading 2 overstated: n=9/fuel, no CI; one week like 25 Sep (38.6 c/L pump–cost gap) can flip it. Better reading: in crises retailers price off pump-side information, not lagged landed cost; try 7, the only big gain, uses pump-side data. Reading 3 stands.

### Proposals, ranked
1. Probabilistic output; calibrate the tiers. 10/50/90 quantiles at h=1–3 from walk-forward adl_ecm residuals; conformal with real-time scaling (trailing crude vol or EWMA |residual|). Tiers from interval width and P(move beyond ±2 c/L). Fixed-width bands mis-cover in both regimes (crisis MAE 2.2–2.5× calm). Falsifier: existing backtest residuals, no refits. Pass: per fuel and h, 80% coverage within 75–85% overall and in 2026; interval score ≥10% better than unscaled conformal in crisis, no worse in calm. Cost 8–10 h, no new data.
2. Fix the scorecard. Trailing (real-time) regime label; per-fuel incl. 95; block-bootstrap CIs on MAE ratios; skill vs naive, directional accuracy, pinball loss; real-time vintages for 2026 (at least undo 23 Sep adjustment). Falsifier: re-score try 1. Pass: all weeks since 2013, MAE ratio <0.97 with 90% CI upper <1.00, each fuel at h=1. Cost 5 h.
3. Fixed-weight combination, gated in real time. 50/50 adl_ecm + try-1 nowcast; nowcast weight → 0 when trailing crude vol or Yahoo–FRED basis (backwardation proxy) exceeds a threshold set on pre-2020 data. Competitions favour simple fixed combinations. Expected 3–5% calm, ~0 crisis. Pass: no fuel×h worse than adl_ecm since 2013, ≥3% better overall, 2026 no worse than +3%. Existing outputs, 4 h.
4. Value-of-information test before seeking a pump feed. Re-run try 7 with fixed 0.5 weight, per fuel. Pass: ≥15% cut in h=1 MAE, CI excluding 0, both diesel and 91 → price a licensed feed; fail → close the line. 3 h.

### Stop doing
- Point MAE as the objective. Freeze adl_ecm as the median; no more slope windows, recency weights, own lags, or a fifth asymmetry attempt.
- Verdicts on n<30 without a CI; post-hoc combinations reported as results.
- Pooling Diesel+91 in research while production reports per fuel; leaving out 95.
- Using the centred label to compare real-time methods.

### Gaps
- How tiers are computed today; were hit rates ever checked.
- Real-time vs revised data in backtests; which vintage of the target is scored.
- Share of crisis weeks, n per regime, production h=3 numbers.
- What readers decide with the report (fill now or wait?).
- Is importer cost built from $1-rounded crude? If so ~±0.6 c/L at the pump — the size of the gains being chased.

