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
- **Served through Imperva's CDN, and the edge can be a week behind the
  origin.** On 19 Aug 2026 the Fabric copy activity (Australia East) read
  the previous week's file from the plain URL while the same request from
  Auckland returned the new one. Any query string bypasses the edge cache
  and reaches origin, so `ingest_mbie_weekly` appends `?cb=<ticks>` per run
  — see `docs/architecture.md`. Publication time that week was 01:01 UTC
  (13:01 NZT) Wednesday, per `last-modified`.

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

**Decomposition identity — it is defined on `Adjusted retail price`, not on
`Board price`.** This file previously stated it with `Board price` on the
left, which is wrong; corrected 14 Aug 2026 after checking numerically.
MBIE's methodology document defines it the other way round
(`Importer margin = Adjusted Retail Price − Taxes and Levies − Importer
cost`), and the data agrees:

```
Adjusted retail price = Importer cost + Taxes + GST + ETS + Importer margin
Price excluding tax   = Importer cost + Importer margin      (ETS is NOT in it)
Adjusted retail price = Price excluding tax + Taxes + GST + ETS
```

| identity, mean absolute error over 1164 weeks | Regular | Diesel | Premium 95R |
|---|---|---|---|
| on `Adjusted retail price` | 0.66 | 0.64 | **0.00** |
| on `Board price` | 6.99 | 6.47 | 4.82 |

Premium 95R closes to **exactly zero on every week**. Regular and diesel
close on most weeks but carry a residual — mean 0.66 c/L, max 11–14 —
which is unexplained and worth locating before the decomposition is relied
on for those two fuels.

**Which target to use for what.** The two differ by the quarterly
adjustment factor, and that has a sharp practical consequence for anything
computed on week-over-week *changes*: the factor is re-based in **169 of
1163 weeks**, average step 0.90 c/L and largest 10.69, against a typical
weekly price move of 2.02 c/L. Those steps are re-basing artifacts, and in
a differenced series they are indistinguishable from real price movement.

- **`Adjusted retail price`** — for decomposition (the identity only holds
  here) and for "what people actually pay".
- **`Board price`** — for measuring timing and response on changes: it
  carries no re-basing steps.
- To strip taxes *without* importing the steps, build the target as
  `Board price − Taxes − GST − ETS` rather than using `Price excluding
  tax`, which inherits them from the adjusted series. Removing GST also
  removes a 15% multiplicative inflation of every response measured on the
  gross price.

**Note:** there is no separate "retail margin" variable in this dataset —
confirmed against both the data dictionary and the actual CSV. Don't assume
it exists; it would have to be derived, if needed at all.

## Every weekly column is a weekly average — including crude, despite the wording

From MBIE's *Data dictionary*
(https://www.mbie.govt.nz/dmsdocument/139-weekely-fuel-price-monitoring-data-dictionary-pdf),
read 14 Aug 2026. `Date` is "the date corresponding to the **Friday** of the
week for which this observation applies" — every row in the file is a
Friday, and the observation is attributed to the whole ISO week.

What each column is, in MBIE's own words:

| column | definition | averaged? |
|---|---|---|
| `Board price` | "The national **average** advertised price for a given fuel **for the week**" | **yes, stated** |
| `Adjusted retail price` | "The national average price paid by consumers for a given fuel **for the week**" | **yes, stated** |
| `Exchange rate` | "The **weekly average** exchange rate" | **yes, stated** |
| `Dubai crude price` | "The Dubai Fateh **spot** crude price" | **not stated** |
| `Importer cost` | "The calculated cost of purchasing the fuel and importing it to New Zealand" | **not stated** |

Where a series is averaged over the week, MBIE says so explicitly; for
crude and importer cost it says nothing, and the word "spot" pointed the
other way. The natural reading was therefore that the project had been
regressing a weekly-*average* target on a point-in-time *spot* factor for
its entire life. **That reading is wrong, and it was settled by measurement
rather than by reading the wording harder.**

### How it was settled — daily Brent as a ruler

`seeds/brent_daily.csv` (FRED `DCOILBRENTEU`, daily, free, no key; 5,650
rows from 2004-04-23, exactly MBIE's start) was loaded purely as a
diagnostic instrument. Brent is a **different grade** from MBIE's Dubai
Fateh, so their *levels* are not comparable — but the grade spread moves
slowly, so on **week-over-week changes** it drops out. Four candidate
constructions were correlated against MBIE's own weekly change, on an
identical sample so the r's are directly comparable:

| candidate for what MBIE publishes | r, all years | r, pre-2022 | r, import era |
|---|---|---|---|
| **Mon–Fri mean of the stamped week** | **0.890** | **0.928** | **0.850** |
| Friday spot of the stamped week | 0.677 | 0.684 | 0.673 |
| Friday spot of the prior week | 0.447 | 0.518 | 0.351 |
| Mon–Fri mean of the prior week | 0.229 | 0.261 | 0.184 |

Not close. A grid search over window end-offset (−5…+2 days) and span
(0…9 days) then pinned the window exactly: the maximum sits at **offset 0,
span 4** — Monday through Friday of the week the row is stamped with.
Wider spans scoring identically are the same set of trading days with
weekends added, which contain no quotes.

The residual 0.11–0.15 is Brent-vs-Dubai grade divergence plus MBIE's
whole-dollar rounding (below), not evidence of a different window.

**So the factor and the target are on the same footing after all.** Both
are Monday–Friday averages of the stamped week. Consequences, revised:

1. **The half-week timing offset does not exist.** Both series are centred
   on Wednesday, so a target and factor sharing a `Date` are genuinely
   contemporaneous. The project's "one week" is one week; there is no
   hidden extra day to subtract. The earlier version of this section
   claimed otherwise — it was inference from wording, and it was wrong.
2. **The averaging is itself a low-pass filter, applied before we ever see
   the data.** Any sub-weekly dynamic — an intra-week spike that reverses
   by Friday — is destroyed at source. No amount of modelling recovers it
   from the weekly file; only daily data can.
3. **"Spot" in the dictionary describes the *price type*, not the sampling
   frequency** — a spot quote as opposed to a futures or contract price.
   It says nothing about how many of them are averaged. Worth remembering
   the next time a single word in the dictionary looks decisive.

### How much the weekly file hides

The same daily series answers a question the weekly file cannot: how large
is the intra-week movement that averaging removes. Per MBIE week, the
Mon–Fri high-minus-low range of Brent, against the change in the weekly
average from the previous week:

| era | n | avg intra-week range | as % of level | avg week-over-week move | range ÷ move | weeks where range > move |
|---|---|---|---|---|---|---|
| pre-2020 | 825 | $2.92 | 4.3% | $2.08 | 1.40 | 69% |
| transition 2020–22 | 108 | $3.33 | 6.6% | $2.59 | 1.28 | 71% |
| import era, calm | 205 | $3.62 | 4.4% | $2.45 | 1.48 | 74% |
| 2026 crisis | 23 | $10.95 | 10.9% | $7.67 | 1.43 | 65% |

**In roughly seven weeks out of ten, crude moves more *within* the week
than the week's average moves *between* weeks.** The ratio is remarkably
stable at 1.3–1.5 across four eras that differ by 3× in absolute
volatility — the crisis scales both numbers up together rather than
changing their relationship.

This does not invalidate anything measured so far: both sides of every
correlation are averaged the same way, so the comparison is internally
consistent. What it bounds is *resolution*. Questions of the form "did the
pump price respond within days" are unanswerable from this file in
principle, not merely unanswered — the answer was averaged away before
publication. That is the strongest argument yet for the daily-benchmark
roadmap item.

*Documentation quirk worth knowing:* the dictionary defines `Importer
margin` as "the **discounted diesel price** less direct taxes and levies,
GST, ETS, and the importer cost" — "diesel" is plainly left over from
copy-paste in a general definition. The rest of it confirms numerically
what is recorded above: margin is struck against the retail price, not the
board price.

## The 2026 provisional weeks: MBIE paused, backfilled, and is waiting on Stats NZ

Read from MBIE's own pages on 16 Aug 2026 (site page updated 12 Aug):
`.../weekly-fuel-price-monitoring` and its child page
`.../weekly-fuels-importer-cost-and-margin-restart-analysis`. This confirms
from the source what was inferred from the regression the same morning.

**MBIE suspended publication of `Importer cost` and `Importer margin` from
18 March 2026 to 1 July 2026** — "in response to increased volatility
resulting from the 2026 Middle East conflict... so we could better
understand these movements". Those weeks were then published
retrospectively. Only those two series were paused; retail prices, taxes,
GST and ETS continued throughout.

**That matches the revision record exactly.** `dbo.mbie_revisions` shows
changes only in `Dubai crude price`, `Importer cost` and `Importer margin`
— zero revisions in `Adjusted retail price`, `Board price`, `ETS`,
`Exchange rate`, `GST`, `Taxes`, `Price excluding tax`, across all 1,164
weeks. The paused series are the revised series.

**"Provisional" does not mean estimated.** MBIE: "data from 1 April 2026 is
currently provisional. Data from 1 April 2026 through 30 June 2026 will be
finalised **when Stats NZ releases the Consumers Price Index data for the
June 2026 quarter**." So the flag marks a *dependency on an external input
not yet available*, not a modelled or interpolated value. This is why the
interpolation fingerprint tests found nothing: there is no interpolation to
find (`docs/architecture.md`).

**When better data arrives:** on the Stats NZ CPI release schedule, quarter
by quarter. April–June finalises with the June-quarter CPI; the weeks after
that follow their own quarters. As of the 13 Aug 2026 data vintage the
whole 3 Apr – 7 Aug stretch was still Provisional.

**A known gap in the cost series, acknowledged by the publisher.** The
Commerce Commission, "in consultation with fuel importers, has also
identified additional costs currently affecting fuel importers", and MBIE
is working with them "to ensure these costs are accurately reflected in our
fuel price data". ComCom's 18 June 2026 report finds the diesel price-cost
spread still above the previous three years. **If `Importer cost` is
missing costs, the residual `Importer margin` is overstated by the same
amount** — which is a documented, publisher-acknowledged reason for
diesel's margin to look extreme, independent of any behaviour.

### MBIE's own findings, and where they agree with this project

Their restart analysis reports numbers this project derived independently.
They match exactly, which is a useful check on the pipeline:

- Lowest margins in the conflict: **diesel −12.4 c/L, regular petrol −0.3**
  — identical to the trough found here on 15 Aug, and MBIE confirms these
  are the first negative margins since the series began.
- Negative weeks: diesel 6 Mar, 13 Mar, 3 Apr; petrol 13 Mar.
- First-week fall: **diesel 42.4 → −2.2 c/L, petrol 37.6 → 15.3** — MBIE
  uses the same 27 Feb pre-conflict baseline that had to be corrected into
  this project on 14 Aug.
- **"There was a one- to two-week lag before domestic pump prices responded
  to the initial surge in international prices."** Independent
  corroboration of the ADL result (peak weight at lag 1, centre of mass
  1.5 weeks petrol / 2.1 diesel) from the body that publishes the data.
- Diesel affected more than petrol; importer-cost sd 50.5 for diesel in
  2026 against 21.1 in the Ukraine conflict, "an order of magnitude larger
  than what has historically been observed".
- Dubai crude US$71/bbl pre-conflict to an all-time high US$156 in three
  weeks.
- Diesel's record margin 103.0 c/L in the week ended 24 Apr 2026.

## Both crude price columns are rounded to whole dollars

Found 14 Aug 2026, after a size-bucketed analysis produced impossible gaps.
`dubai_crude_nzd` and `dubai_crude_usd` contain **zero non-integer values
across all 1164 weeks** (NZD range 29–267, USD 18–156). `exchange_rate`,
`board_price` and `importer_cost` all carry full precision, so this is
specific to the crude series.

Consequences, which matter most for anything computed on changes:

- Weekly crude changes take only integer values. 149 weeks show a change of
  exactly zero and 277 show exactly ±1.
- Rounding error is ±0.5 in the level, so in a week-over-week difference it
  has a standard deviation of about 0.41. Against a typical weekly move of
  1–3 dollars that is 15–40% noise; against the 29–267 range of the levels
  it is negligible.
- Measurement error in an explanatory variable biases a regression slope
  **toward zero**, and worst where the true signal is smallest. Any finding
  of the form "small crude moves pass through less" must be checked against
  this before being read as behaviour — a ratio of means is far more robust
  here than a slope fitted inside a narrow range.
- This also explains why level-based results always looked cleaner than
  change-based ones.

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

## The Singapore quote is observable after all — via Australia (20 Aug 2026)

`Importer cost` is built from an Argus Singapore product quote we do not
have and cannot afford. The Australian Institute of Petroleum republishes
that same Argus quote — Gasoil for diesel, MOGAS95 for petrol, alongside
Tapis and North Sea Dated — in a free weekly PDF, published **Sunday**,
three days ahead of MBIE's Wednesday release.

Checked over 20 diesel weeks and 13 petrol weeks (Oct 2025 – Aug 2026),
converted from AU cents/litre at the RBA-adjacent FRED rate:

| | level correlation | week-on-week changes |
|---|---|---|
| Diesel: AIP Gasoil vs `Importer cost` | 0.9992 | 0.997 |
| Petrol: AIP MOGAS95 vs `Importer cost` | 0.9998 | — |

**So the Singapore benchmark has been in the panel since 2004**, as
`Importer cost` offset by the freight-and-wharfage markup. An additive
offset changes neither correlation nor slope, so anything built on
*changes* — the ADL, the lag work, the crude/crack split — can use
`Importer cost` directly and needs no external product series. That closes
roadmap item 2's "a Singapore product quote is the better new factor" as
already satisfied, for changes-based work.

**The markup is not constant, and diesel's is not petrol's.** Diesel's went
6.9 → 13.4 USD/bbl across those months; petrol's held between 7.4 and 9.6
(sd 0.79). Week to week it moves ~±0.5 against ~±10 in the cost itself, so
it is flat enough for differencing and misleading for levels.

Cause unresolved. Freight and wharfage are **not** ruled out by the fact
that petrol's markup held: petrol and diesel move as segregated parcels on
different vessels, and the route rate can differ by product. The candidates
remain product-specific freight, the quarterly quality premium, and a
widened spread between AIP's 10ppm marker and MBIE's 50ppm high-pour one.
Twenty weeks with gaps cannot separate them.

**There is no archive.** AIP keeps only recent files — 15 diesel and 11
petrol reports when surveyed — and deletes the rest; Mar–Jun 2026, the peak
of the crisis, is already gone. Two things follow: each report carries both
"Last Week" and "Previous Week", so one fetch yields two weeks and a missed
run costs nothing; and `seeds/monitoring/aip_singapore_weekly.csv`
accumulates, so weeks outlive their deletion upstream. That seed is the only
copy of what has been collected — it is appended to, never regenerated, and
moving it into the warehouse was a load, not a re-derivation.

**Fetch via the WordPress REST API, not by guessing URLs.** Upload folders
track the CMS upload date, not the data date — January reports sit under
`2026/02`, August ones under `2026/03` — so brute force found only 12 of 33
candidate weeks. `wp-json/wp/v2/media?search=Weekly-Diesel-Prices-Report`
returns the exact list. The table sits on page 3 of each PDF; the parser is
tied to that layout and will fail loudly if it changes — loudly on stderr,
that is, without a non-zero exit: a restyled Australian PDF is not a reason
to stop recomputing New Zealand numbers, and the store failing to advance is
itself warned about by `aip_latest_week_out_of_step`.

Collected by `research/aip_check.py` (step 1 in `QUICKSTART.md`); the
comparison against `Importer cost` is `models/monitoring/monitor_aip_gap.sql`
and its warn-level tests. This is the only check that can catch a
stale-but-well-formed MBIE file, since everything else we test is downstream
of that same file.

Data is Argus, published by AIP under licence, with their own calculations
layered on. Attribution is required if any of it is republished, including
in the LinkedIn series.

## `Importer margin` is not the importer's margin — read the name as a warning

Established 15 Aug 2026, working back from the identity:

```
Importer margin = Adjusted retail price − Taxes and levies − GST − ETS − Importer cost
```

**It holds exactly from 2010 onwards, and not before.** Checked on all
1,164 weeks × 2 fuels: from 2010 the residual is 0.000 c/L in every single
row, both fuels, every era. Across 2004–2009 it does not reconcile — the
median is still 0, but the 95th percentile of |residual| is 4.4–4.6 c/L and
the worst rows reach 13.8 (diesel, 16 May 2008). Roughly 295 of the 1,164
weeks are affected, all of them before 2010.

That is a structural break in its own right, on top of the 1 Jan 2022
retail-source change already documented below, and it is another
independent reason not to treat the 2000s as commensurable with the present
(the era question raised 14 Aug). Any decomposition that subtracts
`Importer cost` from a retail price is quietly unreliable before 2010,
because the published components do not add up to the published total. Use
2010+ for anything that relies on the identity; the import era (Apr 2022+)
is safer still.

Two things about that line decide how the whole margin analysis should be
read.

**It is struck against the discounted price, not the board price.** The
identity does not close on `Board price` — the pylon-sign number — which
misses by 4.8–7.0 c/L. It closes on `Adjusted retail price`, what consumers
actually paid after loyalty cards and fuel dockets. So retail discounting
is *not* inside the margin; it has already been removed.

**`Importer cost` stops at the wharf.** It is purchase + shipping +
wharfage (above). Nothing downstream is modelled: terminal storage,
domestic coastal shipping and road distribution, station operating costs,
card acquiring fees, and the retailer's own margin. All of it lands in the
residual. **`Importer margin` is therefore a gross margin for the entire
domestic chain, from wharf to nozzle — not an importer's profit.** Any
sentence of the form "importers made X" is unsupported by this column.

Three further things fall into the same residual:

1. **Procurement timing.** `Importer cost` is a replacement-cost estimate
   at this week's Mon–Fri average spot. Whatever was actually paid, and
   whenever it was bought, the model substitutes the week's average — so
   the gap between real purchase price and modelled cost lands in margin,
   with the sign flipped. Buying well shows up as margin, not as lower
   cost. Scale of the effect, from daily Brent: within a rising week there
   is a day cheaper than the previous week's average 25–38% of the time,
   worth ~0.7–1.3 c/L in calm periods and ~3.5 c/L in the 2026 crisis
   (against margins of ~45 c/L, so second-order — but least so exactly
   when the crisis conclusions are being drawn). Two reasons not to
   over-read it: cargo pricing conventionally averages quotes over a
   window around the bill of lading rather than taking one day's print,
   and cargoes are bought weeks ahead, so the relevant week is not the
   stamped one.
2. **Every error in the cost model**, sign-flipped — it is a residual of a
   residual.
3. **Stale quarterly constants** — Worldscale flat rate, freight
   adjustment, insurance, loss factors and wharfage all update quarterly
   while the series is weekly.

### The level drifts hard; the changes do not

Annual mean `Importer margin`, c/L:

| year | petrol | diesel | | year | petrol | diesel |
|---|---|---|---|---|---|---|
| 2004 | 13.5 | 18.2 | | 2016 | 28.2 | 33.3 |
| 2008 | 10.7 | 12.6 | | 2020 | 30.9 | 39.7 |
| 2012 | 20.5 | 23.6 | | 2023 | 35.7 | 45.1 |
| 2014 | 25.4 | 30.8 | | 2026 | 40.6 | 50.6 |

Roughly a tripling over 22 years. That is what the residual construction
predicts: the unmodelled downstream costs it absorbs — trucking, terminal,
station operation — rise with general inflation, and none of it is
deflated. **So the level is not comparable across eras, while
week-over-week changes are**, because those downstream costs are near
constant at weekly resolution. Most of this project's margin work is on
changes and is unaffected.

**Rule for percentiles, learned by getting it wrong.** A full-history
percentile of a margin *level* mostly measures the drift. The failure is
asymmetric:

- For a **collapse**, the full-history yardstick is *conservative* — the
  drift means a low 2026 value must beat the genuinely low 2004–2008 era
  to rank extreme. March 2026's diesel (−12.4) and petrol (−0.3) minima
  have **zero** weeks below them in 22 years. Safe to quote.
- For a **normal-looking level**, it is misleading. Diesel's pre-crisis
  42.4 reads as the 84th percentile of 22 years but the **33rd** of the
  last three; petrol's 37.6 as the 90th versus the **48th**. An earlier
  version of `linkedin_series.md` drew the wrong conclusion from exactly
  this, and has been corrected.

Default to an era-local window (three years) unless the drift demonstrably
works against the claim.

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

**Extended 22 Aug 2026: it is no longer loaded into silver at all.** The
exclusion above was from revision tracking only, so the column still rode
along in `silver_fuel` where nothing read it. Its row was removed from
`seeds/variable_mapping.csv`, which drops both the value and its status
column from the pivot. Bronze still holds the rows; restoring it is the same
one line in reverse. Reasoning: `architecture.md`, "Status belongs to a
value, not to a week".

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
