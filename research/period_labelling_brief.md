# Brief: rebuild the period labelling — for a separate thread

Self-contained. Written 15 Aug 2026 from the main thread, which is
continuing with ADL estimation in parallel and does not need this answer
for another four steps.

## The ask, in one sentence

`seeds/periods.csv` classifies weeks as `crisis` or `calm`. That single
axis is not enough, because the periods it marks contain several unrelated
shocks at once — decide what the right classification is, and produce it.

## Why one axis fails — the March 2022 example

Period `03_ukraine_2022` (24 Feb – 31 Aug 2022) is labelled `crisis`,
meaning "crude shock". Four structural things happen inside or immediately
before it:

| when | what | size |
|---|---|---|
| 1 Jan 2022 | MBIE changed its retail price **source** (Envisory → Datamine) | data regime |
| 24 Feb 2022 | Russia/Ukraine crude shock | the intended label |
| 18 + 25 Mar 2022 | fuel **excise cut**, −21.43 then −3.57 c/L | −25.0 c/L |
| 31 Mar 2022 | **Marsden Point stops refining** — NZ goes fully import-fed | physical chain |

Any comparison of "crisis" against "calm" that includes this period is
comparing a crude shock *plus a tax reform plus a change of supply chain
plus a change of measurement* against calm. The confound cannot be fixed by
moving boundaries; it needs **several independent flags** instead of one
`period_type`.

## What is already established (verified in data — do not re-derive)

Sources: `docs/mbie_notes.md`, `docs/architecture.md`. Facts below were
measured on the panel this week, not assumed.

**Policy steps, exact dates, from the `taxes` column:**

| date | fuel | Δtax c/L | what |
|---|---|---|---|
| 1 Oct 2010 | both | — | **GST 12.5% → 15%** (effective rate exactly 15.000 from this date) |
| 1 + 8 Oct 2010 | petrol | +1.29, +1.71 | excise |
| 6 Jul 2018 | both | +2.89 | Auckland regional fuel tax introduced |
| 18 + 25 Mar 2022 | petrol | −21.43, −3.57 | excise cut (−25.0 total) |
| 30 Jun + 7 Jul 2023 | petrol | +7.17, +17.91 | excise restored (+25.1 total) |
| 5 Jul 2024 | both | −3.42 | Auckland regional fuel tax removed |

Stripping taxes neutralises these: over the two weeks spanning each step,
Δnet price is −1.02, −1.53 and +0.33 c/L respectively, and **no tax week
appears in the 8 largest weekly moves of the net price in 22 years**. But
each step smears across two weeks (e.g. +4.69 then −5.71), which is the
size of a real margin move — those ~6 weeks likely need dummies.

**Data-regime breaks:**

- **Before 2010 the published components do not reconcile.** The identity
  `adjusted_retail − taxes − gst − ets − importer_cost − importer_margin`
  is exactly 0.000 in every row from 2010; across 2004–2009 the 95th
  percentile of |residual| is 4.4–4.6 c/L and the worst is 13.8 (diesel,
  16 May 2008), ~295 weeks affected. Second fingerprint of the same break:
  the implied GST rate wobbles 11.5–13.5% before 2010 instead of sitting at
  12.5%. **Recommend excluding pre-2010 from anything using the identity.**
- **1 Jan 2022** — retail price source changed. Fingerprints: last
  zero-change week 24 Dec 2021; diesel's decimal precision changes.
- **31 Mar 2022** — Marsden Point ceased refining.

**Other things that are not what they look like:**

- `ets` is **not** a policy constant. It is the NZU carbon price × a fixed
  emissions factor (diesel/petrol ratio = 1.1558, sd 0.006 over 16 years),
  so it moves weekly like an asset price and is a random walk
  (autocorrelation of changes −0.07; "unchanged" beats momentum by 68%).
  Treat it as a market factor, not policy.
- Diesel is taxed via road user charges, not at the pump: `taxes` is 1–4
  c/L for diesel against 77 for petrol. The two fuels are not comparable on
  the tax axis at all.

## Current `seeds/periods.csv`

| period_id | type | span | weeks |
|---|---|---|---|
| 01_covid_2020 | crisis | 2020-03-06 → 2020-06-05 | 14 |
| 02_calm_own_refinery | calm | 2020-06-05 → 2022-02-18 | 89 |
| 03_ukraine_2022 | crisis | 2022-02-24 → 2022-08-31 | 27 |
| 04_tariff_2025 | crisis | 2025-04-02 → 2025-06-30 | 13 |
| 05_calm_import_era | calm | 2025-07-10 → 2026-02-27 | 34 |
| 06_iranus_2026 | crisis | 2026-02-28 → (open) | 23 |

**200 labelled weeks out of 1,164. The other 964 are unlabelled** — and
they are not "unknown", they are ordinary weeks. Any crisis/calm comparison
silently drops 83% of the data. How to treat them is part of this task.

Note also `01` ends and `02` starts on the same day (2020-06-05); the
export handles it by taking the first match ordered by `period_id`.

## Candidate events to investigate (NOT yet verified — verify or discard)

Neither the dates nor the existence of an effect are established. Several
may turn out to be invisible in weekly national averages.

- **Auckland pipeline rupture, Sept 2017** — domestic supply shock with no
  crude cause at all. If visible, it is the cleanest possible example of
  why "crisis" needs to distinguish cause.
- **COVID lockdowns** — NZ had strict national lockdowns from late Mar 2020
  and Aug 2021. This is a *demand* shock, opposite in mechanism to a supply
  shock, yet `01_covid_2020` labels it the same way as `03` and `06`.
- **1 Jul 2018** — Auckland regional fuel tax introduction (the data shows
  the step on 6 Jul 2018).
- **2008 financial crisis** — a demand collapse, currently unlabelled, and
  inside the unreliable pre-2010 window.
- **Marsden Point refinery outages / maintenance before 2022** — would show
  as supply constraints during the own-refinery era.
- **NZ ETS quarterly auction dates** — public and known in advance. Worth
  testing whether `ets` volatility clusters around them.

## Suggested output

1. `docs/period_labelling.md` — findings, with the same discipline as the
   rest of the project: what was measured, on what data, what was
   discarded and why.
2. A **proposed** replacement seed, as a new file (e.g.
   `seeds/period_flags.csv`), with independent boolean/categorical columns
   rather than one `period_type` — something along the lines of: crude
   shock (and direction), policy change, data-regime change, domestic
   supply event, demand event. The exact schema is part of the question,
   not given here.
3. A recommendation on the 964 unlabelled weeks.

## Rules and constraints

- **Do not edit `seeds/periods.csv`, `models/`, `docs/architecture.md` or
  `docs/mbie_notes.md`.** The main thread is working in those. Propose a
  new seed alongside; the merge is a later decision.
- Data is local and offline: `research/data/panel_weekly.csv`, 1,164 weeks
  × 2 fuels, 2004-04-23 → 2026-08-07, no gaps, no missing values.
  Regenerate with `python research/export_panel.py` only if new weeks are
  needed (requires `az login` and the Fabric capacity running).
- Python env: `source /Users/Ray/nz-fuel-price-project/.venv/bin/activate`
  (note: one level **above** the project dir). pandas/numpy/scipy/
  statsmodels are installed.
- **Verify empirically before asserting.** This project has retracted five
  documented findings in two weeks; every one died to an unchecked
  assumption. If an event's effect cannot be seen in the data, say so
  rather than labelling by narrative.
- Watch the yardstick: `importer_margin` levels have tripled since 2004, so
  full-history percentiles measure drift, not behaviour.
- The Fabric capacity auto-pauses at 23:00 NZT and starts billing real
  money on 28 Aug 2026. Prefer the offline CSV.

## What the answer feeds

Step 7 of the ADL plan in the main thread: testing whether pass-through
speed and completeness change in a crisis, by interacting the model's
shape parameters with a regime flag. That test is only as good as the flag,
which is why this is worth doing properly rather than inheriting six
hand-drawn periods.
