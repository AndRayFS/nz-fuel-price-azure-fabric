# Draft — NZ Fuel Price Project, Part 6 (costs)

Style checked against `linkedin_series.md`. Numbers sourced from
`cost_notes.md` (Cost Management + Consumption APIs, pulled 10 Aug 2026).

**Open item before posting:** whether to name the Part 3 currency error
explicitly (recommended: yes, it's the best beat in the post).

The 9 Aug reading (12.00 h instead of 14) is resolved: the data simply
hadn't fully landed when it was pulled on 10 Aug. Re-pull before posting
if you want the settled figure — it should firm up to ~14.

---

## Post — 2974 / 3000 UTF-16 units (LinkedIn's counter)

LinkedIn counts UTF-16 code units, not characters: the bold
`𝗡𝗭 𝗙𝘂𝗲𝗹 𝗣𝗿𝗶𝗰𝗲 𝗣𝗿𝗼𝗷𝗲𝗰𝘁 — 𝗣𝗮𝗿𝘁 𝟲` header is 30 visible characters but
costs 53 units, and 💡 costs 2. Headroom is 26 units — re-count after any
edit. The `lnkd.in` backlink is already included at its real length (24).

Last time the report went live. This time, the bill.

When I created the Fabric capacity in Part 3, the portal showed $306.60 a month and I felt a small jolt of panic. I reported it as NZ$306.60.

It wasn't. It was US$306.60 — NZ$531 at the rate Azure actually billed me. Same session, two currencies: my credit in New Zealand dollars, the capacity estimate in US.

❓ So what did a full platform — bronze to gold, dbt, a published Power BI report — actually cost?

NZ$58.79. 28 July to 9 August.

✅ NZ$57.93 of that bought nothing at all. It's the capacity being switched on.
✅ NZ$0.86 paid for every warehouse query, every dbt run, every Spark job, every OneLake read and write, and every view of the report. Combined, over thirteen days.

98.5% versus 1.5%.

I'd assumed an idle capacity would be cheap and a busy one expensive. It's the opposite: the workload is almost free, and availability is what you pay for.

The clearest evidence: 8 August. The capacity was awake fourteen hours. Nothing ran on it — no queries, no pipelines, no report views. The bill was NZ$10.19, identical to the day before, when I used it.

💡 F2 costs US$0.21 per capacity-unit-hour, and an F2 is two of them: NZ$0.73 for every hour it's switched on, query or no query.

Which makes the pause schedule the only thing that mattered.

✅ Average uptime: 6.1 hours a day, not 24.
✅ Thirteen days at 24/7 would have been NZ$227. I paid NZ$58.79 — 74% saved.
✅ It leaves a fingerprint: 7 and 8 August bill for exactly 14.00 hours each, the precise 09:00–23:00 window I'd scheduled. I never had to open the Logic App to confirm it worked; the invoice already had.

Three things that cost time rather than money:

1️⃣ Budget alerts fire once per threshold per period — notifications, not brakes. I ended up with a ladder at 50/100/150/200%.
2️⃣ Azure reports costs in UTC whatever the UI timezone says. At UTC+12, everything I did before lunch landed on the previous day's report.
3️⃣ The query editor in Lakehouse Explorer defaults to Spark SQL, not T-SQL. One routine-looking check spun up a Spark session — NZ$0.16, almost the whole Spark line for the project.

And the one that isn't a footnote: a paused capacity makes the published report unreachable. Not stale — gone. The pause schedule I was proud of and the live report I published are in direct conflict. Either the capacity runs 24/7 at NZ$531/month, or the report has opening hours.

That's why the live link became a PDF.

The honest limitation: thirteen days on the smallest capacity is not a benchmark. It says what a solo weekend project costs — the only claim I can support.

Six posts in: the MVP is successfully migrated to Azure and Fabric. Next, back to the data — connecting the sources I sketched in Parts 2 and 3, and the methodology itself.

Still cheaper than the coffee I drank writing it. ☕

𝗡𝗭 𝗙𝘂𝗲𝗹 𝗣𝗿𝗶𝗰𝗲 𝗣𝗿𝗼𝗷𝗲𝗰𝘁 — 𝗣𝗮𝗿𝘁 𝟲

Part 5: https://lnkd.in/e0000000

#MicrosoftFabric #Azure #DataEngineering

---

## First comment

Cost figures pulled from the Azure Cost Management and Consumption APIs
rather than the portal — the `usageDetails` endpoint is the one that
exposes `unitPrice`, `pricingCurrencyCode` and `exchangeRate`, which is how
the US-dollar mix-up became obvious.

Repo: https://github.com/AndRayFS/nz-fuel-price-azure-fabric

## Cut to fit 3000 — swap back in if something above earns less

Costs are in UTF-16 units, so you can trade directly.

- **Reporting lag (~200)** — "Cost data is officially 8–24 hours behind. In
  practice one day's figure kept climbing between checks more than a day
  apart — NZ$0.68 became NZ$1.34 for the same date." This is the one real
  loss: it answers a question Part 3 asked publicly and left open.
- **9 August explanation (~180)** — that 12.00 h instead of 14.00 h is the
  lag caught in the act. Only worth including alongside the item above.
- **The caching irony (~250)** — "The dashboard isn't querying anything
  live when you open it — it's a cached snapshot, refreshed at most every
  30 minutes. And it still needs a paid, running capacity just to hand you
  that file."
- **Credit line (~90)** — "Total damage: NZ$58.79, comfortably inside the
  NZ$354 trial credit."

Cheapest thing to drop if you want the reporting-lag item back: the honest
limitation paragraph is ~155, or plain-text the bold Part 6 header to save
23.

## Cut for length — available if you want a different angle

- Publish to Web: Microsoft's own community gave directly contradictory
  answers on whether it consumes capacity, and learn.microsoft.com doesn't
  resolve it. Good "not everything about money is documented" beat.
- The tenant-admin saga to enable Publish to Web at all: Fabric
  Administrator role via the original owner account, ~15 min to propagate,
  two separate tenant switches, plus a false alarm from a stale UI cache
  warning about Block Public Internet Access.
- Publish to Web caches for up to 1 hour; 30 minutes is the hard floor on
  refresh frequency.
