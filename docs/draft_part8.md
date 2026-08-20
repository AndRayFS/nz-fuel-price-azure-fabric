# Part 8 draft — what a litre is made of, and what actually moves it

Status: **drafted 20–21 Aug 2026**, not yet published.
Format: a short post around one animated GIF, deliberately half the length
of Part 7 — the picture carries the argument.

Spine: Part 7 closed on "crude barely moved, diesel's landed cost went up
61%". This post answers it by taking the litre apart — six layers on the
left, how much each of them actually moved on the right — and shows that the
biggest slice is rarely the one doing the moving. It ends by naming the one
layer the model structurally cannot see: the week currently in progress.

House style, hashtag conventions and the correction log: `linkedin_series.md`.

## The picture

`research/art/anim.py` builds `fuel_price_anatomy.gif` — 81 frames (one
title card, then every month from Jan 2020 to Aug 2026), 24.5 s, 1.77 MB,
1100×632. Run it from its own directory; it reads `fonts/*.ttf` and
`research/data/panel_weekly.csv` by relative path and writes the GIF beside
itself.

The companion page, with the two static Sankeys, the layer cards and the
model's scope drawn as a flow, is published as an artifact:
https://claude.ai/code/artifact/d79fff09-9908-4f3d-b574-c58794fcd989

**Left column** — the six layers in cents per litre, monthly means:
crude (Dubai, converted at that week's FX), refining + shipping
(`importer_cost` minus crude), NZ chain + margin (`importer_margin`),
fuel excise, ETS, GST.

**Right column** — for each layer, the mean *absolute* weekly change over
the preceding six calendar months, also in cents per litre. Absolute is the
whole point: the column measures how restless each layer has been, not which
way it went, so a layer that swings ±10 c/L and ends where it started still
reads as tall. Two consequences worth remembering before quoting it:
opposing layers cannot cancel out, and the column's total is therefore
larger than the average weekly move of the pump price itself.

Both columns hold a fixed scale across the whole clip, so 2026's jump is
visible as height rather than as a number in a caption.

Six layers, not seven. The static Sankey splits refining from shipping;
the animation cannot, because Argus product quotes only reach back to Oct
2025 (`mbie_notes.md`), so the two stay merged for the years before that.
The first cut of both the GIF's title card and the post said "seven" —
caught 21 Aug, before publication.

## Fact-check trail

Recomputed 21 Aug 2026 against `research/data/panel_weekly.csv`, diesel,
monthly means where the post quotes a month.

| claim in the post | verified value |
|---|---|
| crude up about 20% since late February | +21.8%, 27 Feb → 14 Aug 2026 |
| landed cost up 70% | `importer_cost` +72.9%, same window |
| Apr 2020: a litre costs 113 cents | 113 c/L (22 + 19 + 46 + 4 + 7 + 15) |
| Apr 2020: crude is 22 of them | 22.4 c/L |
| Apr 2020: wharf-to-tank is 46 | `importer_margin` 45.6 c/L |
| crude ≈ a quarter of everything else | 22 against 91, i.e. 24.6% |
| Mar 2026: the layer goes negative | weekly: −2.2, **−12.4**, +2.7, +17.7 |
| lowest in 22 years | −12.4 on 13 Mar; 3 weeks below zero in 1,165, all 2026; series starts 23 Apr 2004 |
| Aug 2026: refining 92 vs crude 87 | 92.4 and 86.9 c/L, monthly means |
| a quarter of the whole effect | lag-0 share 26.3% (petrol ADL, `draft_part7.md`) |
| GST 15% | rate since 1 Oct 2010; whole series is post-2010 for tax purposes |

Two deliberate wordings, both of them corrections of things the earlier
drafts got wrong:

- **"The market now pays more for turning the barrel into diesel than for
  the barrel itself"** — not "costs more". The crack spread is the market's
  price for finished product over crude, i.e. gross revenue to refining, not
  refinery opex, which barely changed. The earlier phrasing implied refiners
  were spending three times as much.
- **"in the weekly data it briefly goes negative"** — the monthly frames
  average March to +1.5 c/L, so without "in the weekly data" the text
  contradicts the picture it sits next to.

The post also never says "importer margin". The layer is described by what
it covers — wharf to nozzle — because in the data it is a residual against
a replacement-cost estimate, not anyone's measured profit. Calling it
someone's margin is the exact error the Part 1 audit corrected
(`linkedin_series.md`).

**When to recheck:** the 19 weeks from 3 Apr 2026 are still `Provisional`;
`importer_cost` and `importer_margin` are the two suspended series, so every
2026 figure above is exposed. Re-run `research/export_panel.py` after
Stats NZ publishes the June-quarter CPI, then rebuild the GIF and diff this
table. The Apr 2020 numbers are Final and will not move.

## The draft, ~1,900 characters

```
In my last post I ended on a puzzle. Everyone says pump prices follow oil.

Since late February, crude is up about 20% — and the cost of diesel landed
at a New Zealand wharf is up 70%.

So I took a litre apart.

Left: the six layers that make up a pump price.
Right: how much each of those layers actually moved, week to week, averaged
over the six months before that frame. Both sides are in cents per litre.

The two sides are not the same picture. That's the point — the biggest slice
is rarely the one doing the moving.

Three moments worth pausing on:

1️⃣ April 2020. A litre costs 113 cents. Crude is 22 of them. Everything
between the wharf and your tank — terminals, trucks, running the station —
is 46. The raw material is about a quarter of everything else in the price.

2️⃣ March 2026. The layer that covers everything from wharf to nozzle
collapses to nothing, and in the weekly data it briefly goes negative — the
lowest in 22 years of records.

3️⃣ August 2026. Refining and shipping reach 92 c/L against 87 c/L for crude.
The market now pays more for turning the barrel into diesel than for the
barrel itself.

⚠️ Two caveats. The right-hand column is a six-month average, so it smooths
and lags. And MBIE's weeks from April 2026 are still provisional — those
numbers may be revised.

Not all of these layers need to be forecast. Excise is announced, so you look
it up rather than predict it. GST is arithmetic — 15% on top of everything
below it. The market-driven layers are where forecasting actually becomes
useful.

Which is where the awkward part starts.

My model only sees weeks that have already been published, so it's blind to
the week happening right now — and that week carries about a quarter of the
whole effect.

Turns out that's fixable.

Next time.

NZ Fuel Price Project — Part 8 ☕

#DataVisualization #NewZealand #Energy #DataAnalytics
```

## Notes on choices

- Hashtags carry no `#dbt` or `#DataEngineering`: this post is about the
  data, not the stack. They come back on the post that is about the stack.
- Links to GitHub and to the public report go in the **first comment**, per
  the series convention.
- No point-forecast language. The closing promise is about the *method*
  ("turns out that's fixable"), not about where prices go.
- The closing tease is the nowcast: a Monday Brent-in-NZD reading explains
  30% (diesel) / 45% (petrol) of the current week's cost change, which is
  how lag 0 becomes usable. Designed and validated, **not yet implemented**
  in `research/backtest.py` — Part 9 should not be written until it is.
