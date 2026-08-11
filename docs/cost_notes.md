# What the project actually cost on Azure / Fabric

Source: Cost Management REST API (`ActualCost`, daily, grouped by Meter),
subscription `e30d2fa4-…`, pulled 10 Aug 2026. Reproduce with:

```bash
az rest --method post \
  --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.CostManagement/query?api-version=2023-03-01" \
  --body @cmquery.json
```

(`az consumption usage list` is not usable — it deserialises `pretaxCost`
as the string `"None"`. `az costmanagement` needs an extension that isn't
installed. The API throttles with HTTP 429; retry with backoff.)

## Headline numbers

| | NZD |
|---|---|
| Total, 28 Jul – 9 Aug 2026 (13 billed days) | **58.79** |
| — Fabric capacity sitting awake (`Compute Pool Capacity Usage CU`) | 57.93 (98.5%) |
| — everything else combined | 0.86 (1.5%) |

"Everything else" is the entire data platform doing actual work: warehouse
queries 0.29, Spark 0.16, all OneLake read/write/storage operations 0.36,
data movement 0.03, Power BI 0.01. Logic Apps rounded to 0.0000.

**The point for the post:** you don't pay for what you compute, you pay for
the capacity being awake. Thirteen days of building, running dbt,
backtesting and publishing a report cost 86 cents. Keeping the lights on
cost NZ$57.93.

## Uptime, derived from CU-hours

F2 = 2 CU, so `CU-hours ÷ 2` = hours the capacity was actually on.

| Date | CU-h | NZD | hours on |
|---|---|---|---|
| 28 Jul | 0.04 | 0.02 | 0.0 |
| 29 Jul | 2.98 | 1.11 | 1.5 |
| 30 Jul | 2.62 | 0.98 | 1.3 |
| 31 Jul | 6.99 | 2.60 | 3.5 |
| 1 Aug | 8.26 | 3.01 | 4.1 |
| 2 Aug | 5.52 | 2.01 | 2.8 |
| 3 Aug | 7.39 | 2.69 | 3.7 |
| 4 Aug | 14.53 | 5.29 | 7.3 |
| 5 Aug | 18.94 | 6.89 | 9.5 |
| 6 Aug | 11.69 | 4.25 | 5.8 |
| 7 Aug | 27.99 | 10.18 | **14.0** |
| 8 Aug | 28.00 | 10.19 | **14.0** |
| 9 Aug | 23.99 | 8.73 | 12.0 |

7 and 8 August land on 13.99 and 14.00 hours — exactly the 09:00–23:00
window the Logic App pair was scheduled for. The schedule did what it was
supposed to, to the minute, and the billing data proves it independently.

9 August shows 12.0 h rather than 14 because the day had not finished
arriving when this was pulled on 10 Aug — the reporting lag, not a
schedule change. Re-pull for the settled figure; expect ~14.

Average across the 13 days: 6.1 h/day, i.e. the capacity was asleep ~75%
of the time.

## Inside 7 and 8 August

No hourly detail exists — Fabric emits one usage record per meter per day
(`date` is always `T00:00:00Z`), so 14.00 h is a daily total, not a
timestamped window. Per-meter, those two days looked like this:

| meter | 7 Aug | 8 Aug |
|---|---|---|
| Compute Pool Capacity Usage CU | 10.1826 | 10.1864 |
| Data Warehouse Capacity Usage CU | 0.0053 | — |
| Power BI Capacity Usage CU | 0.0033 | — |
| OneLake ops (all kinds, combined) | 0.0049 | — |
| OneLake Storage Hot Data Stored | 0.0001 | 0.0001 |
| Consumption Built-in Actions (Logic Apps) | 9 actions, 0.0000 | 9 actions, 0.0000 |

8 August is the cleaner illustration of the whole point: the capacity was
awake for 14 hours and **nothing ran on it at all** beyond storage sitting
there. Same NZ$10.19. 7 August had a little warehouse and Power BI
activity — under one cent of it.

The Logic App pair shows up as exactly 9 built-in actions per day, billed
at zero.

## Savings from pausing

Effective measured rate: **0.36447 NZD per CU-hour**, so F2 costs
**0.729 NZD/hour** while running.

- 13 days at 24/7 would have been NZ$227.43
- actual: NZ$58.79
- **saved NZ$168.64 (74.2%)**

## The 306.60 figure is USD, not NZD — Part 3 has a currency error

Resolved from `Microsoft.Consumption/usageDetails`, which exposes the
pricing fields the Query API hides:

| field | value |
|---|---|
| `unitPrice` = `payGPrice` = `effectivePrice` | **USD 0.21** per CU-hour |
| `unitOfMeasure` | 1 Hour |
| `pricingCurrencyCode` / `billingCurrencyCode` | USD / NZD |
| `exchangeRate` | 1.7325 (constant across all 9 days) |
| `pricingModel` | OnDemand |
| `meterRegion` | AU East |
| `isAzureCreditEligible` | true |

F2 = 2 CU, so `0.21 × 2 × 730 = ` **USD 306.60 per month** — exact, to the
cent. The portal's monthly estimate was in **US dollars**; Part 3 published
it as "NZ$306.60". In NZD that same 24/7 month is **NZ$531.18**
(306.60 × 1.7325), which matches the NZ$532 implied by measured spend.

Worth noting the trap rather than hiding it: the credit figure quoted in
the same post (NZ$354) *is* in NZD — roughly USD 200 at this rate. So the
portal showed credit in local currency and the capacity estimate in USD,
in the same session. That is a genuinely good beat for Part 6, and more
honest than quietly restating the number.

## Reporting latency (open question from Part 3)

Part 3 asked publicly about cost-reporting latency and left it unanswered.
Measured on 10 Aug 2026: the most recent day with data was 9 Aug. So usage
surfaces with roughly a day's lag, not hours. That closes the loop on a
question the series already posed — a good, honest beat for Part 6.

## Current state (11 Aug 2026)

`nzfuelcapacity` (F2, Australia East) is **Paused** — suspended 14:09 NZT
on 11 Aug via `az rest .../suspend`, confirmed `Paused` at 15:19. The
auto-resume Logic App stays disabled for good; auto-pause stays at 23:00
NZT permanently. With Report 1 now served from My Workspace (see below),
the capacity is only needed for the weekly `dbt run`.

Trial credit was NZ$354 (Part 3). NZ$58.79 spent implies ~NZ$295 left, but
the credit balance was **not** read from the API — treat as arithmetic, not
a measurement.

## Reconciliation with the author's running notes

The author kept notes through the project (13 theses, 10 Aug 2026). Where
they meet the billing API:

**Confirmed exactly.** Accidental Spark experiment ≈ NZ$0.16 — the
`Spark Memory Optimized Capacity Usage CU` meter totals **0.1603** across
the whole project, so that one experiment is essentially the entire Spark
line. Daily figures 28 Jul 0.02 / 29 Jul 1.34 / 30 Jul 1.01 all match to
the cent. Logic Apps "fractions of a cent" is generous — they bill
**0.0000**, 9 built-in actions per day, inside the free grant.

**The reporting-latency note is corroborated.** The author watched one
day's figure climb NZ$0.68 → NZ$1.34 across two checks more than 24 h
apart; the API's final value for 29 July is **1.3354**. So the number they
saw second was the settled one, and the official "8–24 hours" understates
it. Independently: on 10 Aug the most recent day with any data was 9 Aug.

**Correction 1 — thesis 6 is no longer an open question.** The note says
Compute Pool is "~NZ$1/day regardless of actual work, and the mechanics are
disputed even in Microsoft's own community". The billing data settles it:
the meter is priced per **CU-hour** (USD 0.21), and quantity tracks uptime
at exactly 2 CU. It is not ~NZ$1/day — it is **0.729 NZD per hour the
capacity is awake**, which ranged 0.02 to 10.19 NZD/day here. 8 August is
the proof: 14 hours awake, *zero* warehouse/Spark/Power BI activity, full
NZ$10.19. Charged for being on, not for working. Publish this as answered,
not as "I don't know".

**Correction 2 — thesis 11's "~$260/month".** The correct 24/7 figure is
USD 306.60 = **NZ$531.18**.

**Correction 3 — thesis 1's hook is stronger than written.** See the
currency section above: 306.60 was USD, and Part 3 published it as NZD.

**Caveat on thesis 3/4 (UTC).** The author's own note that Azure bills in
UTC regardless of the UI timezone applies to every date in this document —
all tables here are UTC days. For NZT (UTC+12) that shifts things by half a
day. It happens not to distort the 7–8 Aug uptime reading: a 09:00–23:00
NZT window is 21:00–11:00 UTC, so each UTC day still contains 11 h from one
NZT day plus 3 h from the next = 14 h. The 12.00 h on 9 Aug is incomplete
data rather than a schedule change (pulled 10 Aug, mid-lag).

**Thesis 13 superseded.** The Google Sheets → Looker Studio escape route is
not the near-term plan. As of 10 Aug 2026 the stated position is: the MVP
is successfully migrated to Azure + Fabric, and the next work is
connecting the additional sources described in Parts 2 and 3 plus
methodology (isolating crude from FX and freight). ~~Keep the always-on
viewing problem as a stated constraint, not as a pending migration.~~ The
always-on viewing problem was solved on 11 Aug 2026 without leaving the
stack — see "The always-on claim was wrong" below.

## Angles available for Part 6

1. 98.5% / 1.5% split — the cost of being awake vs the cost of working.
2. The pause schedule paid for itself: 74% saved, verifiable in billing data.
3. Billing data as an audit trail — the 14.00 h rows independently confirm
   the Logic App worked, without looking at the Logic App.
4. The Part 3 latency question, now answered (~1 day).
5. ~~The honest tension already recorded in `architecture.md`: a Fabric
   report is only viewable while capacity runs, which is what forced the
   PDF switch — and is a real point in GCP's favour.~~ **Wrong, and Part 6
   published it anyway (11 Aug 2026).** See below — this is now Part 7
   material, not Part 6 material.

## The always-on claim was wrong (11 Aug 2026)

Part 5 said "a paused Fabric capacity makes even a published report
unreachable". Part 6 sharpened it to "Not stale. Gone." and framed it as a
binary: 24/7 at ~NZ$531/month, or the report keeps opening hours. Both
posts are live with that claim.

It is true only for a workspace backed by an F capacity — which is how this
project was set up — and not a property of Power BI.

**Verified, capacity paused throughout:**

| | |
|---|---|
| Capacity suspended | 14:09 NZT, 11 Aug |
| Report checked | 15:19 NZT — 70 min later, past the 1 h publish-to-web cache |
| Capacity state at check | `Paused` (read from ARM) |
| Result | report renders **with data** |
| Cost to serve | NZ$0 |

What changed: semantic model and report republished to **My Workspace**
(shared capacity, not the F2), shared via **Publish to web**. New URL is on
`app.powerbi.com`; the old `app.fabric.microsoft.com` embed code is dead.

**Constraints that come with this route:** import mode only (no
DirectQuery, no live connection), model and report in the same workspace,
no report-level DAX measures, and everything in the model is publicly
readable — fine here, the source is public MBIE data.

**Second correction in the same area:** F2 never bought viewer-licensing
relief. Free viewers on capacity-backed workspaces start at **F64**. The
capacity was paying for compute, never for sharing.

**Open, and the reason not to over-claim in public yet:** the account is 46
days from the end of a Power BI Pro trial (~26 Sep 2026), and it is
unresolved whether publish-to-web from My Workspace survives on a Free
licence. Graph shows `POWER_BI_STANDARD` / `BI_AZURE_P0` and no Pro SKU in
the tenant, so the trial looks like it is tracked inside Power BI rather
than Entra. Microsoft's docs point both ways. Check the link the day after
the trial ends.

**Part 7 angle.** The strongest version is the reversal: blamed the
platform, published the complaint, then found the constraint was
self-inflicted configuration — plus the licensing detail that the capacity
was never buying what it appeared to buy. Correction comments drafted for
both posts; the author is publishing them by hand.
