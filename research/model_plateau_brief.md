# Model plateau — review brief, 7 Nov 2026

Self-contained: a reviewer should need nothing but this page. Numbers are
quoted from `docs/research.md`; scripts are in `research/` and `pipeline/`.

> **Known errors, found after the panel ran** (review, section 3), left as
> the reviewers read them:
> - There are no confidence tiers (sections 1, 8). Report 1 states
>   uncertainty as a band on Now and a Track record page.
> - The run is on Thursday at 09:07 NZ, not on Wednesday (sections 1, 2).
> - The 18 Sep Yahoo point (section 2) was not wrong. It was the next
>   futures contract (`docs/research.md`, 7 Nov 2026).

## 1. The product

A public Power BI report (Report 1) and a phone page, refreshed by an
unattended weekly load each Wednesday after MBIE publishes. It shows where
New Zealand pump prices are likely to go over the next 1–3 weeks given what
crude and landed cost have already done. Readers are the general public and
the owner, who shows it in person from a phone. The report uses confidence
tiers and must not use point-forecast language ("will be", "predict").

## 2. The forecast task

- **Target:** MBIE's weekly national-average pump price, c/L, horizons
  h = 1, 2, 3 weeks. Three fuels: Diesel, Regular Petrol (91), Premium
  Petrol (95). The averages are computed and published by MBIE by its own
  method; the project does not compute them and cannot change how they are
  built.
- **Made:** in the Wednesday run, after MBIE publishes. MBIE's newest week
  (week t) ends on the preceding Friday, so at the run the data is about five
  days behind reality. Getting information about the current week from
  third-party sources has been one of the improvement lines (tries 1, 2, 7).
- **Known at that point:**
  - MBIE's weekly series through week t: importer cost, crude as a Mon–Fri
    mean, taxes, margin.
  - Daily Brent from two free sources, no database needed. FRED: spot only,
    no futures, and several trading days behind. Yahoo: front-month futures,
    and the only source that has the first days of the current week by
    Wednesday. Its endpoint is undocumented, and one point has already been
    wrong: 18 Sep 2026 showed 98.77 against about 103.5 elsewhere.
- **Not known at that point:** daily pump prices. ComCom's daily national
  average exists from Feb 2026 but is published fortnightly. The only timely
  source (Gaspy) is crowd-sourced and unlicensed.

## 3. How a model is judged

- Walk-forward backtest: refit at every cutoff on data up to that week only.
  Training from 2010, 156-week minimum, forecast origins since 2013.
- Metric: MAE in c/L on the pump price (model carries its own GST
  conversion). **Production always reports MAE per fuel.** The research
  tests in section 6 pooled Diesel and Regular Petrol unless stated, and did
  not include Premium 95.
- **One model per fuel, with coefficients shared by all weeks.** The regime
  label plays no part in the forecast. Errors are split by it after the
  fact, in Report 1 and in the backtest, into non-crisis and crisis weeks.
  "Crisis" is a volatility regime: sd of weekly % changes of crude over a
  **centred** 9-week window, so the label is not known when a forecast is
  made.
- Each test has a pass rule written before it is run.

## 4. Production model and baselines

`adl_ecm` (`pipeline/backtest.py`): weekly change in the pump price net of
tax regressed on cost changes at lags 0..6, plus an error-correction term
(the margin's distance from its trailing 104-week mean). Expanding window.
The h-week forecast may only use lags k ≥ h, i.e. only cost moves already
observed.

| MAE c/L | naive (no change) | adl_ecm |
|---|---|---|
| non-crisis, h=1, petrol / diesel (2010+, 15 Aug) | 1.93 / 1.89 | 1.42 / 1.37 |
| non-crisis, h=2, petrol / diesel | 3.52 / 3.44 | 2.74 / 2.65 |
| research, Diesel + Regular pooled, since 2013, h=1, non-crisis / crisis | — | 1.40 / 3.08 |
| research, Diesel + Regular pooled, since 2013, h=2, non-crisis / crisis | — | 2.70 / 6.62 |
| 2026 (Feb–Oct, 38 wk), h=1, diesel / petrol | 11.19 / 6.30 | 6.15 / 2.31 |

20–27% better than naive across fuels, horizons and regimes; beats naive in
59–65% of weeks.

## 5. Data facts that matter

- Nine volatility episodes in 22 years. The 2026 one carries most of the
  recent error and is the sample for most recent tests.
- The crude→cost slope, fitted by year, ranges 0.67–2.03; diesel 2026 is
  2.03 against a long-run 1.23.
- In some 2026 weeks the pump moved against cost: diesel, week of 25 Sep,
  cost −17.5 c/L, pump +21.1 c/L.
- MBIE revises history: weeks are Provisional until a quarterly
  finalisation, and on 23 Sep 2026 a cost adjustment was added to every week
  from 27 Feb 2026, including weeks already Final.
- Crude in the source is rounded to whole dollars.

## 6. What has been tried

| # | Idea | Pass rule (before run) | Result |
|---|---|---|---|
| 1 | Nowcast week t+1's cost from Brent futures, inside the ADL | beat `adl_ecm` | **PASS**, 8 Sep. Non-crisis weeks (n = 597): −6–8% MAE at h=1, −12–14% at h=2–3. Crisis weeks of the six past episodes that reach the forecast sample: −9–15%. Whole 2026 episode, Mar–Oct: still ahead, −2.0% at h=1, −10.2% at h=2 *(corrected 7 Nov; the first version gave non-crisis only)* |
| 2 | Same nowcast in the backwardation window only: a sub-window of the 2026 episode, nowcast weeks from 4 Sep | no worse than `adl_ecm` at h=1, 2 | **FAIL**: +13.5% h=1, +7.4% h=2. Spot or ComCom input instead of futures: no better at h=1, even though they nowcast cost 3–4× better. n = 9 per fuel. Not promoted, not run in shadow |
| 3 | Rolling-window crude→cost slope for the nowcast | — | Diesel 52-week window gets the 2026 slope almost right (1.94 vs 2.03) and gives the worst 2026 forecast. Expanding window kept |
| 4 | Recency weighting, WLS half-life 3 years | beat production | **FAIL**: +0.1–1.5%; rolling 5-year window worse by 2–5% |
| 5 | Two own lags of the pump price, recursive | beat at h=1, 2 non-crisis, not lose in crisis | **FAIL**: +1.9–5.8% non-crisis; one gain (diesel h=1 crisis −8.8%) gone by h=2 |
| 6 | Asymmetry ("rockets and feathers"), fourth attempt | detect a difference | Not detected for either fuel (CIs wide) |
| 7 | Ceiling: use ComCom's daily pump prices for Mon–Tue of week t+1 | direct reading beats production by 20% | Direct: −10.9%, rule not met. Post-hoc combination with production: **−48% at h=1**, −20% h=2, −10% h=3; 60 calls, all in 2026, mostly diesel |

Earlier: the report's original formula lost to naive and was withdrawn.

## 7. Current readings in the project — interpretations, challenge them

- Specification changes on the same data are not helping.
- In crisis weeks the pump is not following cost through the fitted
  pass-through, so better cost inputs make the forecast worse.
- Crisis pass-through is not identified: claims about crises rest on very
  few episodes.

## 8. Constraints

- One person, part-time. Research runs offline on a published data archive;
  the warehouse is billed per hour and is avoided.
- No licensed timely pump-price source today; whether to seek one is open.
- The regime label, as defined today, cannot be used to switch methods at
  forecast time: it needs weeks that have not happened yet.
- The project consumes MBIE's averages as published and does not rebuild
  them.
- Output must stay compatible with confidence-tier framing.

## 9. The question

Improvement of the forecast has stalled: the attempts above did not beat
production. Review the situation and say what you would do next.
"Stop working on the point forecast" and "the target or the evaluation is
wrong" are acceptable answers.

## 10. What to return (≤ 600 words)

1. **Diagnosis:** why attempts are failing — up to 5 bullets, each tied to
   evidence in this brief that supports or contradicts it.
2. **Proposals, ranked (3–5):** what; why; expected effect; the cheapest test
   that could falsify it; the pass rule you would write before running; cost
   in hours and data.
3. **Stop doing:** what you would drop.
4. **Gaps:** what in this brief you would want verified or is missing.
