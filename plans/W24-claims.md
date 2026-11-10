# W24 — claims inventory of `docs/research.md`

Prepared 10 Nov 2026 as input to `findings.md` for W24 ("contradictions first,
then a 'what holds now' header", `docs/workstreams.md`). A working list, not a
document of record.

- **Against `d6c91dd`** (main, 10 Nov 2026). `L` is the heading's line at that
  commit; it drifts with any edit.
- **37 sections** (`## `), all listed. The preamble (L1–19) and
  `# Appendix — withdrawn` (L2771) are not sections.
- **Date.** From the heading where it has one; `(corrected)` / `(withdrawn)`
  marks a heading date that is the correction's, not the finding's.
  `≈` = first commit containing the heading text,
  `git log -S '<heading>' --reverse --date=short`, no path filter, so history
  from before the 3 Sep 2026 split out of `docs/architecture.md` counts. None
  resolved to the split commit itself.
- **Marker.** `top` = a block quote at the section's top (the file's own
  "overtaken" rule); `in body` = a correction written into the text; `none`.
- **Numbers** are as written in each section: illustrations from its date, not
  recomputed.
- **Order.** Topics as below; within a topic by date, then by line.

| Topic | Sections |
|---|---|
| Lag structure | 7 |
| Pass-through decomposition & asymmetry | 2 |
| ADL model | 7 |
| Crisis definition & sample | 2 |
| Cost composition & margin | 3 |
| Backtest & walk-forward | 4 |
| Nowcast | 7 |
| Brent price source | 4 |
| Method checks | 1 |
| **Total** | **37** |

## Claims

| Section (heading · line) | Date | Topic | Key claims | Source | Marker |
|---|---|---|---|---|---|
| Diesel's "lag shift" was a flat peak, not a regime change — corrected 13 Aug 2026 · L109 | 2026-08-13 (corrected) | Lag structure | "Diesel 3, petrol 2" rests on a 0.0053 r-gap for diesel (0.9000 vs 0.8947), against petrol's 0.0627.<br>No 3-week shift: the 8 May 2→3 move is the max-lag cap `min(10, weeks//3)` lifting.<br>The real finding is an 8-week convergence: r@2 0.729→0.895, r@3 0.962→0.897. The margin hypothesis is untested. | `lag_resolved` (`lag_confidence_gap`); expanding-window query | in body: "This section previously reported … does not survive" (13 Aug) |
| Crude lands on `Importer cost` at lag 0 — and what that does and doesn't prove · L199 | ≈2026-08-13 | Lag structure | `importer_cost` peaks at lag 0 (gap 0.19–0.70 in crisis periods vs 0.003–0.07 for board price). That is the arithmetic of a replacement-cost series, not market speed.<br>MBIE data cannot split the crude→board lag into procurement and pricing.<br>The refinery-era break is a range-restriction artifact and is dropped. The 06_iranus_2026 cost looks damped (CV ratio 0.53). | — | in body: "drafted and then withdrawn", "ruled out" (13 Aug) |
| Rolling window over all 22 years — the single-best-lag method is weakly identified · L261 | ≈2026-08-13 | Lag structure | Share of decisive windows (gap ≥ 0.05), diesel/petrol, 1164 wks 2004–2026: 13w 46.8/44.4%, 26w 17.7/16.2%, 52w 9.1/5.5%.<br>The lag profile is a smooth unimodal hill (runner-up adjacent in 92–100% of windows), so a small gap means a broad hill. Flat profiles are trend artifacts.<br>After 2022 diesel's modal lag moves 1→2 and petrol's does not; the Envisory→Datamine switch (1 Jan 2022) confounds it. | — (26w sweep, lags 0–8) | in body: "Finding 1, as first written, was wrong"; "Finding 2 … is withdrawn" (13 Aug) |
| Levels vs changes — the project has always correlated levels, and it matters · L376 | ≈2026-08-13 | Lag structure | On weekly changes the peak is ~5× better separated (diesel gap 0.149 vs 0.031) and r drops ~0.23, so the published r is optimistic by ~0.2.<br>2026 episode on changes: diesel lag 3 (by 0.126), petrol lag 1.<br>Per-lag slopes do not add up (diesel sum 2.224 vs levels slope 0.976), so weights need a joint ADL. | `lag_correlation_series` | none |
| Lag stability separates crisis from calm — an unplanned finding · L2836 | ≈2026-08-13 | Lag structure | *Withdrawn.* The expanding-window best lag sits still in shocks (0 transitions in 01_covid_2020 and 06_iranus_2026 petrol) and wanders in calm (27–28 transitions in 02_calm_own_refinery). Read as confirming the `periods.csv` labels.<br>Proposed a gap-keyed stability signal and a health warning on calm-period `resolved_lag`. | expanding-window run; `periods.csv`; `resolved_lag` | appendix: withdrawn by L2778; no quote of its own |
| Lag stability separates crisis from calm — WITHDRAWN 15 Aug 2026 · L2778 | 2026-08-15 (withdrawn) | Lag structure | On 2010+ against `crude_vol_regime` the contrast does not reproduce: high-vol weeks are *less* stable. Best lag changed in 17.4/18.3% of weeks (n=109) vs 14.5/12.7% normal (n=724).<br>04_tariff_2025 is not "mislabelled". The within-period measure is too weak to separate crisis from calm either way (gaps 0.004–0.081). | `periods.csv`; `crude_vol_regime` | top: "Correction, 15 Aug 2026, to the withdrawal itself"; appendix |
| Does old crude reach the pump? Petrol: no. Diesel: not shown. · L1488 | ≈2026-08-16 | Lag structure | Petrol: crude from wks 4–12 adds +0.022 (p 0.77; detectable above 0.146). A clean null, consistent with replacement-cost pricing.<br>Diesel: +0.246 (p 0.19; detectable above 0.371), so "not shown". The 9-lag block is jointly significant (p 0.0007) but sums to +0.010 ± 0.131.<br>Old crude does not extend the 1–3 wk horizon (2010+). | `research/procurement_lag.py` | none |
| Pass-through, decomposed — and three versions of an asymmetry finding that did not survive · L541 | ≈2026-08-14 | Pass-through decomposition & asymmetry | Diesel's landed cost is 1.5–2.4× more crude-sensitive than petrol's, in the import era only (pre-2020 ~0.39 vs 0.37). The cost side, not the retailer, is why diesel differs.<br>Importer margin moves *with* crude, and more so at longer horizons (diesel 0.127/0.264/0.440/0.621 at 2/3/4/6w).<br>Diesel's up/down asymmetry is in cost (0.762 vs 0.554 at 2w → 1.037 vs 1.031 at 6w), not the pump. | — | in body: three asymmetry findings "died" |
| Rockets and feathers, fourth attempt: still not there · L1534 | ≈2026-08-15 | Pass-through decomposition & asymmetry | No asymmetry (2010+, K=6, ECM, 861 wks). Rise−fall: petrol +0.052 [−0.19, +0.33] p 0.61, diesel +0.291 [−0.11, +0.53] p 0.20.<br>Diesel's HAC p is 0.062 against a block-bootstrap 0.204; use the bootstrap.<br>Power is ±0.26 petrol / ±0.32 diesel: evidence of absence at that size, silence below it. | `research/adl_asymmetry.py` | none |
| The distributed-lag model, first results — 15 Aug 2026 · L729 | 2026-08-15 | ADL model | Petrol total pass-through is 0.92–1.03 at K=3..12, and the CI covers 1.0. Peak at lag 1; 69–85% arrives within 3 wks.<br>Non-crisis pass-through is stable and complete for both fuels. Diesel spread 0.123 in normal vs 0.450 in high-vol weeks; the crisis sum is not identified.<br>ECM: petrol −0.084…−0.109, diesel −0.096…−0.122; half-life ~6 wk. | `research/adl_baseline.py`, `research/adl_ecm.py`, `analyses/lag_levels_vs_changes.sql` | in body: "Superseded 15 Aug — see 'Scoped correctly'". Subsection top quote "magnitude is dated, 29 Aug" → L1072. "What the creep is: the 2026 crisis, and nothing else" is unmarked |
| Canonical results — FINAL data only, 16 Aug 2026 · L950 | 2026-08-16 | ADL model | Recommended quote: diesel complete ~0.93–1.02 (Final, excl. 2026); petrol Final 0.952–1.070.<br>ECM: petrol −0.103 (half-life 6.4 wk), diesel −0.094 (7.0). No stable intensity gradient.<br>Walk-forward h=2 non-crisis MAE: petrol 3.519→2.796, diesel 3.440→2.669. In volatile weeks the mean lag roughly halves (held as provisional). | `research/headline_results.py`, `export_panel.py` | top: "Superseded in part, 29 Aug" → L1072. Subsection top quote "Half of this is gone, 29 Aug". in body: crisis-week edge downgraded (16 Aug) |
| The diesel instability is Provisional data, not the crisis - 16 Aug 2026 · L1254 | 2026-08-16 | ADL model | Claimed that dropping 19 Provisional weeks moved diesel's spread 0.326→0.098. This does not survive (29 Aug: 0.320→0.223).<br>What survives is the process rule: exclude Provisional weeks, or report with and without them.<br>The mechanism is unknown; neither segment looks interpolated. | `dbo.mbie_revisions` | top: "Superseded 29 Aug; note added 3 Sep" → L1072. in body: "What this retracts" (the 15 Aug creep claim) |
| The quarter finalised, and it answered the question — 29 Aug 2026 · L1072 | 2026-08-29 | ADL model | Finalisation is a level shift (diesel −1.861, petrol −0.848 c/L) and cancels in differences.<br>"Diesel is fixed" was premature: Final diesel K=3/6/9/12 is 0.850/0.902/1.087/1.073, spread 0.223. The excl-2026 figure is unchanged (0.930/1.006/1.020/1.012).<br>The regime speed effect is gone in petrol (p 0.159) and stronger in diesel (p 0.0036). Skill vs naive, non-crisis: 27.2% h=1, 22.5% h=2. | `research/headline_results.py`, `backtest.py` | top: "Superseded in part, 24 Sep" → L1182, plus a second quote "Reproduced 19 Sep, unchanged … the current set". in body: "'Diesel is fixed' was premature" |
| MBIE added a cost to the crisis, and diesel moved again — 24 Sep 2026 · L1182 | 2026-09-24 | ADL model | MBIE's 23 Sep change adds 70% of the fuel differential to cost from 27 Feb 2026 (max diesel +49.4 c/L). Every movement is the revision.<br>Diesel incl. 2026 is below one at every K: 0.711/0.802/0.988/0.996, spread 0.285. Half-life: diesel 4.0, petrol 5.9 wk. Diesel Δβ₀ +0.050 (p 0.25), not significant.<br>The excl-2026 figure and the h=2 backtest MAE are unchanged. The Final filter does not protect against source rewrites. | none named (re-run on the 24 Sep panel) | in body: "that digit was a slip" |
| The 2026 Final weeks halved diesel's weights; recency weighting does not help — 5 Nov 2026 · L2556 | 2026-11-05 | ADL model | Recency weighting FAIL: WLS with a 156-wk half-life gives MAE +0.1…+1.5%; a rolling 5-yr window is worse by 2–5%.<br>Diesel Σb0..b6: 0.814 on Final weeks to end-2025, 0.444 with 2026; ~60% of the fall is MBIE's adjustment. Regular: 0.817→0.760.<br>Training on 2010–2025 only fails as specified (+5.5% h=1). As a `--live-status` diagnostic it gives −11.1% h=1 (16–17 origins): a direction only. | `research/adl_decay.py`, `research/adl_train_cut.py` | in body: "The specification was wrong" (5 Nov) |
| The pump price's own lags add nothing the cost lags do not carry — 5 Nov 2026 · L2625 | 2026-11-05 | ADL model | p=2 lags of `d_net` FAIL against production: non-crisis MAE +1.9/+5.5/+5.8% at h=1/2/3. The only gain is diesel in crisis at h=1 (−8.8%).<br>The lags take weight from cost (diesel cost-weight sum 0.444→0.121, φ₁ +0.41).<br>p=1 is worse than p=2 everywhere. | `research/adl_ar.py` | none |
| "Crisis" means four different things in this project. Say which. · L1318 | ≈2026-08-15 | Crisis definition & sample | Four senses: news event (`seeds/periods.csv`), crude volatility (`crude_vol_regime`, centred, unusable in a forecast), lag identifiability, and magnitude (not implemented).<br>Thresholds belong in percent with a trailing baseline (weekly crude sd by era 3.87/3.20/5.30/5.70%).<br>Volatility attenuates down the chain. A pump-side regime would agree on only 48% (petrol) / 59% (diesel) of high weeks. | `seeds/periods.csv`, `crude_vol_regime` | none |
| n = 1. Every crisis claim in this project rests on one episode · L1378 | ≈2026-08-15 | Crisis definition & sample | 2026_iran_us crude sd is 13.2% vs Ukraine's 7.8% (1.7× over the episode, 3.1× in the worst week). No comparable upward shock is in the record.<br>As corrected: the 2010+ high regime is 109 wks / 6 episodes. Excluding 2026 (82 wks / 5), diesel's spread is 0.200 vs 0.433 with 2026, so high volatility alone does not change pass-through.<br>n = 1 holds only for episodes of this size. | `seeds/period_flags.csv` | in body: "Corrected 15 Aug — 'n = 1' was too strong"; heading not updated |
| What a litre is actually made of, in cents · L617 | ≈2026-08-15 | Cost composition & margin | Week of 7 Aug (as of 24 Sep): diesel cost 177.2 (65.9%), margin 41.0, total 268.9; petrol cost 127.3 (42.3%), margin 43.9, total 300.8.<br>Diesel fuel tax is 0.9 c/L vs petrol's 77.3 (RUC). Two-thirds of a diesel litre is commodity; petrol is 43% tax and so damped. | — | top: recomputed 24 Sep, claims stand |
| What actually drove pump prices through the 2026 crisis — it is not margin · L645 | ≈2026-08-15 | Cost composition & margin | 27 Feb → 7 Aug (as of 24 Sep): diesel +81.7 c/L = cost +70.1 (86%), margin −1.0, taxes +12.5. Petrol +47.9 = cost +33.6 (70%), margin +6.4, taxes +7.9.<br>Margin dipped and recovered (diesel 83rd → 0.2nd → 82nd pct), so its net contribution is ~nil.<br>The driver is the crude→product spread (diesel cost per unit of crude 0.900→1.353), which a crude-only model cannot see. | — | top: recomputed 24 Sep, conclusion strengthens. in body: "Corrected 14 Aug … reverses the conclusion" |
| What the record says after a margin compression — 19 Sep 2026 · L2446 | 2026-09-19 | Cost composition & margin | As of 24 Sep: a gap ≤ −40% against the lagged trailing 104-wk mean happened once per fuel, in 2026 only (7 petrol, 14 diesel wks).<br>Deepest readings: diesel 3 Apr (−217%), petrol 13 Mar (−127%).<br>A compression marks a cost move that has not reached the pump yet. It does not say which side closes the gap. | `research/margin_episodes.py` | top: "Recomputed 24 Sep — the finding holds, several figures under it do not". in body: two earlier versions withdrawn |
| Backtesting the forecast: does it actually predict anything, or just fit history? · L20 | ≈2026-08-04 | Backtest & walk-forward | Six hand-run cutoff tests. "Direction correct 4/4" is not skill. What survives is the method (`simulate_cutoff_date`) and the gate withholding a forecast at r 0.36–0.50.<br>Error grew with lag length (lag 3 off by 4.6–7.3%), as an observation only. The diesel causal reading is dropped (lag 2 vs 3 r gap 0.004). | dbt var `simulate_cutoff_date` | top: superseded as evidence by the walk-forward test (L1577), 15 Aug, note 3 Sep. in body: "Superseded 11 Aug" |
| The forecast measure multiplies a change by a slope fitted on levels · L448 | ≈2026-08-14 | Backtest & walk-forward | `resolved_slope` (levels) is ≈1.7× the slope on k-week changes (diesel 1.67×, petrols 1.71×).<br>Crisis replay: MAE 6.7% diesel, 1.9–2.0% petrol. It under-predicts the fall, having no intercept.<br>A fitted slope alone cuts MAE 23–25%. | — (`resolved_slope` replay) | none |
| Walk-forward test — the first number in this project that is a forecast · L1577 | ≈2026-08-15 | Backtest & walk-forward | 2010+, 703 wks/fuel. In non-crisis weeks ADL+ECM beats naive by 20–27% on MAE (h=2: petrol 2.743 vs 3.519, diesel 2.650 vs 3.440) and wins 59–65% of weeks; ~20% in crisis.<br>The Report 1-style formula is worse than naive at h=1 (+26%) and wins 39%.<br>Caveats: current vintage, K=6 fitted on the full sample, regime split ex post. | `pipeline/backtest.py` | none |
| The reconstructed published formula loses to doing nothing — withdrawn from the backtest 7 Sep 2026 · L496 | 2026-09-07 (withdrawn) | Backtest & walk-forward | `report1_ish` beats naive at h=2 in only 34.5% of weeks (`adl` 56.4%, `adl_ecm` 55.5%).<br>On the 13 wks finalised 26 Aug: h=1 MAE 15.18 vs naive 7.42.<br>Removed from the pipeline and the model. | `pipeline/backtest.py`, `seeds/forecast_history.csv` | in body: "Withdrawn from the pipeline on 7 Sep" |
| The week in progress is partly visible — 8 Sep 2026 · L1641 | 2026-09-08 | Nowcast | The backtest drops b0 at h=1, so it assumes the coming week's cost does not move.<br>A 3-day Brent-in-NZD nowcast of `d_cost` (970 wks) cuts RMSE 17.5% for diesel and 32.1% for petrol. Three days give ≈95% of the 5-day ceiling.<br>It nowcasts `importer_cost`, not the pump price. Brent is the available benchmark, not the right one. | `research/nowcast_brent.py` | none |
| The nowcast survives the walk-forward test — 8 Sep 2026 · L1716 | 2026-09-08 | Nowcast | Inside ADL+ECM, non-crisis n=597, MAE gain at h=1/2/3: diesel 6.0/13.4/13.7%, petrol 7.6/13.6/12.4%; 9–15% in crisis.<br>The placebo (last week's reading) makes it worse by 1.9–6.7%.<br>The gain is 18–25% in the fifth of weeks with the largest moves. It cannot be switched on by regime (the window is centred). | `research/nowcast_in_adl.py` | none. "What has to be true before this ships" was overtaken by W23 (9 Nov) |
| A better crude-to-cost slope made the forecast worse — 8 Sep 2026 · L2385 | 2026-09-08 | Nowcast | Crude→cost slope: 1.010 petrol, 1.232 diesel; unstable by year, 0.67–2.03.<br>Rolling windows do not help: diesel's 52w slope is 1.94, yet its 2026 MAE is 15.773 vs 13.998 expanding.<br>Keep the expanding window. A sharper b overshoots through the unchanged ADL coefficients. | `research/nowcast_in_adl.py --nc-window N` | none |
| The nowcast in the backwardation: it loses, and spot would not have saved it — 5 Nov 2026 · L1872 | 2026-11-05 | Nowcast | Pre-registered rule, weeks from 4 Sep 2026: FAIL, MAE +13.5% h=1 and +7.4% h=2 (n=9/8). Spot and ComCom do not fix h=1.<br>The cost reading improved and the pump forecast got worse, so the model's response to cost is what fails. Before the backwardation the nowcast helped (+4.3/+12.5%).<br>No timely retail series: TGPs are too late, ComCom is fortnightly, Gaspy → Datamine with terms unknown. | `research/nowcast_backwardation.py`; archive 2026-11-05 | top: "Re-judged 7 Nov" → L1986 |
| Seeing this week's pump price would halve the one-week error — the ceiling, 5 Nov 2026 · L2653 | 2026-11-05 | Nowcast | ComCom's daily average tracks MBIE's weekly price: r 0.998/0.997, slope 1.03 (37 wks).<br>Pre-set rule (beat production at h=1 by 20%) not met: −10.9% (3.763 vs 4.226 c/L, 76 calls).<br>Post hoc, production plus a 2-day reading gives −48% at h=1 (60 calls): a ceiling. The only timely source is Gaspy, whose data Datamine manages; the licence question goes there. | `research/retail_ceiling.py`; ComCom `RETAIL_PRICES_AVG` | none |
| The backwardation veto does not survive a confidence interval — 7 Nov 2026 · L1986 | 2026-11-07 | Nowcast | 90% block-bootstrap CI: the 8 Sep "better" stands. Non-crisis 2013+, n=598: −6.7% [−10.6, −2.6] h=1, −13.5% [−17.0, −10.2] h=2.<br>The backwardation "worse" is not detectable: +13.5 [−11.8, +32.2], n=9/8. Crisis (119 wks, 7 episodes): −10.0 / −13.7%.<br>The recency-weighting FAIL stands. The veto is gone. | `research/verdict_ci.py` | none. "Whether to promote" was overtaken by W23 |
| Wednesday is worth two points at h=2 and h=3, nothing at h=1 — 8 Nov 2026 · L2168 | 2026-11-08 | Nowcast | Wednesday's data against `adl_ecm`, pooled 2013–2026, 711 wk/fuel, calm weeks: h=1 −0.1 [−1.2, +0.9], h=2 +2.0, h=3 +2.3 pts. Crisis ~+1.5, not significant.<br>Live Wednesday bar vs settlement: median 0.17% / p95 0.84% up to 27 Feb 2026, 0.41% / 2.25% after. Corrects W23's "at worst about 0.4%".<br>Keep Wednesday. If it is missing, fall back to the 2-day nowcast, not to `adl_ecm`. | `research/nowcast_in_adl.py --days 2/3` (scratch, not committed) | in body: corrects W23's text |
| The nowcast's Brent is futures, and in this market that is the wrong price — 19 Sep 2026 · L1822 | 2026-09-19 | Brent price source | Yahoo `BZ=F` vs FRED spot: r 0.9964 over 4,714 days. From 1 to 15 Sep 2026 the gap widened 0.5%→20.3% (backwardation).<br>As revised: spot is right for levels in a backwardation, not for the weekly change.<br>"Production unaffected" is stale after W23. | `research/nowcast_brent.py` | top: "Answered 5 Nov" → L1872; "Revised 7 Nov" → L2050 |
| Yahoo's Brent rolls twice, and the roll is real for MBIE's cost — 7 Nov 2026 · L2050 | 2026-11-07 | Brent price source | `BZ=F` daily bars are settlements of the calendar front contract. The live view switches 4–9 trading days earlier.<br>In roll weeks (29% of origins) the nowcast does better (−9.6/−15.8/−15.3%). D1 is not met for petrol h=1 in crisis non-roll weeks.<br>The roll reaches MBIE's cost (b_basis/b_spot 0.73 [0.38, 0.88]), so a live nowcast must request the contract by symbol. | `research/roll_weeks.py`, `research/roll_cost.py` | in body: "Ruled out 10 Nov" → L2306 |
| Yahoo's Brent at the load's own moment: a ceiling of half a cent — 9 Nov 2026 · L2236 | 2026-11-09 | Brent price source | At 09:07 NZT, last trade vs settlement over 51 Wednesdays: median 0.26%, p95 1.59%, max 1.84%. This is a ceiling.<br>The hour of reading hardly matters.<br>Effect on the forecast (95): median 0.02–0.05 c/L, max 0.16/0.37/0.47 at h=1/2/3, against MAE 1.42/2.67/4.04. Nothing to fix; moving the load is open. | `research/nowcast_live_gap.py` | none |
| The roll step reaches MBIE's cost without FRED, and trading leaves the front the day Yahoo switches — 10 Nov 2026 · L2306 | 2026-11-10 | Brent price source | The roll step is real in `importer_cost` (26 roll wks): b_step 2.71 [1.63, 3.78] vs b_same 2.43, ratio 1.12 [0.71, 1.80]. Mechanism unknown (Argus, quarterly constants and FRED are ruled out). Small in practice: MAE 5.21 vs 5.29 c/L.<br>The front carries 22–31% of volume, 8% in expiry week. `BZF27` out-traded `BZZ26` on 22 Oct and Yahoo switched on 23 Oct (one roll).<br>The next-morning daily bar holds the settlement (one observation). | `research/roll_same_contract.py`, `research/roll_volumes.py` | none |
| Checks that have repeatedly changed the answer · L2720 | ≈2026-08-14 | Method checks | Six checks to run before writing a finding down; each has overturned one.<br>Compare slopes, not r. Measure from the last week before the period (in 06_iranus_2026 this turned 6% into "two-thirds").<br>MBIE's "spot" is the Mon–Fri mean. The source rewrote history on 23 Sep: check `revisions_rewrote_a_final_week` (108 rows). | `periods.csv`, `docs/mbie_notes.md` | none |

## Notes for W24

What the four readers flagged beyond the six items already in
`docs/workstreams.md`, W24. Not re-verified line by line.

**Supersession chains point one hop only.** Cite the end of each chain:

- L950 → L1072 → L1182 (pass-through sums, diesel spread).
- L729's ECM quote → L1072 (half-life 5.5/6.1); L1182 has 4.0/5.9.
- L950's speed effect → L1072's regime-speed subsection → its own 24 Sep
  quote (Δβ₀ +0.050, p 0.25).
- L1822's "Answered 5 Nov" → L1872, which L1986 re-judged on 7 Nov.

**Headings that contradict their own body or quote.**

- L950 "Canonical results": no longer canonical.
- L1254 "Provisional data, not the crisis": its top quote says the central
  claim fails.
- L1378 "n = 1": corrected in the body (W24 item 2).
- L2653 "would halve": the pre-set rule was not met (−10.9%); −48% is post hoc.
- L2625 "add nothing": diesel in crisis at h=1 is −8.8%.
- L1072: two top quotes of opposite tenor ("Superseded in part, 24 Sep" over
  "Reproduced 19 Sep … the current set").

**Top quote present, but the body still asserts the overturned figures.**

- L645: body +46% / 61% / 84th pct vs quote +50% / 65% / 83rd.
- L2446: body −64.1% / −54.6% and a closing sentence the quote withdraws.

**Overtaken by W23 (9 Nov) with no marker.**

- L1716 "What has to be true before this ships" (W24 item 3).
- L1986 "whether to promote"; L1872 "Not promoted", "Not run in shadow".
- L1822 "Nothing in production is affected".
- L496 "backtest runs four methods", "the report charts `pred_adl_ecm`". It is
  now five methods with `nowcast`, and Report 1 plots `pred_nowcast`.
- "Production" in L2385, L2556, L2625 and L2653 means `pred_adl_ecm`.

**Stale "Wednesday run"** (the run is Thursday 09:07 NZ; W24 item 4). Found in
four sections: L1641 "a Wednesday production run cannot", L1716 "inside the
Wednesday chain", L1872 "By the Wednesday run" and "misses the Wednesday run",
L2653 "When the Wednesday run makes its calls". Not run references, leave them:
"MBIE publishes weekly, on the Wednesday", and the roll sections' "nowcast's
Wednesday". None before L1641.

**Counts and conventions drift for the same claim.**

- Crisis sample: 109 wks / 6 episodes (L1378), "six episodes" (L1716),
  119 wks / 7 episodes (L1986), 115–117 crisis wks (L2168). Where the seventh
  episode comes from is not stated.
- Non-crisis n: 703 (L1577), 597 (L1716), 598 2013+ (L1986), 717 origins
  (L2050), 711 wk/fuel (L2168).
- Sign: gains are positive in L1716 and L1872, while negative = better in
  L1986.
- Same day, 16 Aug: L950 has Final diesel 1.006–1.104 "more than complete,
  resting on 8 obs", while L1254 has 1.006–1.100 "complete and stable". Spreads
  0.324→0.095 vs 0.326→0.098.

**Duplicate.** "Defect in the backtest record" sits at the end of both L376 and
L448 (W24 item 6). L376's "accuracy on petrol" also contradicts L448, where
petrol under-predicts too.

**Time-limited wording.**

- L2050: "`BZF27.NYM` until 30 Nov 2026".
- L2236: "from 12 Nov".
- L2556: "the next check is the September-quarter finalisation" (not arrived;
  ~25 Nov).

**Out of date order.** L1254 (16 Aug) comes after L1182 (24 Sep). L2385 (8 Sep)
and L2556–L2653 (5 Nov) come after the 10 Nov section.

**Smaller items.**

- L199: "15 of 18 rows" from an 8-row table.
- L541: "0.39 vs 0.37" is not derivable from its table, and it says "32 cells"
  with 16 shown.
- L261: two subsections labelled "Finding 3".
- L376: cites "0.57–0.66 … (see above)", which is not above.
- L1378: leftover references to a range column that is no longer there.
- L1822: "8 c/bbl" is likely USD 8/bbl.
- L20: "Superseded 11 Aug" points to a correction dated 13 Aug.
- L2778: the withdrawal note says 2025 is "not 'mislabelled'", then blames
  "the mislabelled windows".
- "roadmap item N" (L20, L109, L261, L645, L2836) predates `workstreams.md`.

**Dates.**

- L2720: the heading is from 14 Aug, but its six-check form is from 24 Sep
  (4c16a2e).
- L645: "Corrected 14 Aug", yet the section first enters git on 15 Aug.
- L199 and L1378 were dated by a heading fragment, because of quoting.
