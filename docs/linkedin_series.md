# LinkedIn series — index and house style

Derived from reading all seven published posts (Parts 1–5 read 10 Aug 2026,
Part 6 on 11 Aug). Links live in `README.md`.

**Part 7 published 18 Aug 2026:** https://lnkd.in/p/ejjH8i-z — text as drafted
in `draft_part7.md`.

| Part | Topic | Ends by promising |
|---|---|---|
| 1 | Original R lag analysis, MBIE data, 4 shocks | — |
| 2 | Architecture: bronze/silver/gold, metadata pivot, why dbt | "register Azure, stand up Fabric" |
| 3 | Azure/Fabric registration, F2, budget alerts, first pipeline | "bring dbt into the picture" |
| 4 | dbt on Fabric, macros, lineage, the lag bug found vs R | "build the Power BI reports" |
| 5 | Report 1 live, confidence framing, 9am–11pm window | "a look at what all this actually cost in Microsoft Fabric" |
| 6 | Costs: 98.5%/1.5% split, USD/NZD error, pause savings | **"back to the data: new sources, and extending the methodology"** |
| 7 | Backtest: the published formula lost to "no change"; the report gets its own scorecard | **"everyone says prices follow oil — crude +10.1%, diesel's landed cost +61.4%"** |

Each post opens by referring back to the previous one and closes by naming
the next.

## Published corrections

Kept here so the record of what the posts claim stays accurate — the post
bodies were deliberately **not** edited, since the series is
learning-in-public and the reversal is the story.

- **11 Aug 2026, Parts 5 and 6 — the always-on claim.** Part 5 said "a
  paused Fabric capacity makes even a published report unreachable"; Part 6
  sharpened it to "Not stale. Gone." and framed a binary of 24/7 at
  ~NZ$531/month versus opening hours. That holds only for a
  capacity-backed workspace, not for Power BI. Correction comments were
  published on both posts the same day: Report 1 now serves from My
  Workspace via Publish to web, renders with data while the F2 is paused,
  and costs nothing to serve. The comments also state plainly what is still
  unknown — whether this survives the Power BI Pro trial ending ~26 Sep
  2026 on a Free licence. Both carry the new `app.powerbi.com` link; the
  dead `app.fabric.microsoft.com` embed code was left live on purpose,
  since the comment explains it. Full detail in `cost_notes.md` and
  `architecture.md`.

The reversal itself is queued as Part 7 material.

## Audit of Part 1's claims against what is now known (14 Aug 2026)

Part 1 was written from the R analysis, before the Fabric rebuild found any
of the data issues since documented. Re-checked here so the next post
corrects rather than repeats. Post text re-read from LinkedIn on 14 Aug.

**Holds, and was understated — by more than first checked.** "During the
sharpest week of the current crisis, petrol and diesel margins briefly fell
to zero—or even negative." The first pass here quoted −2.2 c/L for diesel,
which was the *first observation inside the period* (6 Mar), not the
trough. The actual minimum is **13 Mar: diesel −12.4, petrol −0.3 c/L —
neither has ever been lower in 22 years, zero weeks below, in either the
full history or the last three years**. At the crude peak (20 Mar) diesel's
2.7 has been undercut in 3 weeks ever, petrol's 7.7 in 13. "Briefly fell to
zero" undersells an outright record.

The margin trend (below) works *against* this finding rather than
manufacturing it: margins have roughly tripled since 2004, so a 2026 value
that lands under the 2004–2008 floor is a stronger result than the
percentile suggests, not a weaker one.

**Holds.** "Diesel margins later rebounded to roughly twice their usual
level" — 93.7 on 19 Jun, against a two-year mean of 47.2. And "the much
smaller 2025 shock showed almost none of that behaviour" — margins through
Apr–Jun 2025 sat at the 85th–98th percentile with no collapse at all.

**Holds.** The forward-looking line — crude up on 17 July, pump prices not
yet moved, "we should begin seeing that change around the end of July" —
came true: diesel +9.4 c/L on 24 Jul and +13.4 on 31 Jul.

**Needs restating.** "As retailers absorbed costs faster than they could
adjust prices." Two problems: the series is the **importer** margin, not
the retailer's; and MBIE computes it as a residual against a
*replacement-cost* estimate (this week's Singapore spot at this week's FX),
so a cost spike collapses the published margin mechanically, whether or not
anyone's actual costs moved — the fuel in the tanks was bought earlier. The
absorption is real but smaller than the number implies. Say "the published
margin collapsed" and offer the mechanism as an interpretation.

**Incomplete rather than wrong — but not in the way first written here.**
The post caught the compression phase only. The follow-up story is *not*
"margins ended far above where they started": measured from the correct
pre-crisis week (27 Feb, not the first week inside the period), diesel's
margin went 42.4 → 47.6 and contributed 6% of the 83.5 c/L price rise,
against 78% from landed cost. **Correction, 15 Aug 2026:** an earlier
version of this paragraph said margin "was already at the 84th percentile
before the crisis". That is a full-history percentile, and margins have
tripled since 2004, so the yardstick measures the drift. Against the last
three years, diesel's pre-crisis 42.4 sits at the **33rd** percentile and
petrol's 37.6 at the **48th** — middling to slightly low for their own era,
not elevated. The real follow-up is that **crude rose 10% while
diesel's landed cost rose 61%** — the crude-to-product spread did the work,
and a crude-only model cannot see it. Rockets and feathers is the dip
itself, not the destination.

**Confounded, and not knowably either way.** The structural explanation —
that the lag lengthened because Marsden Point closed in March 2022 — cannot
be attributed. MBIE switched its retail price source on **1 Jan 2022**, 13
weeks earlier, and that switch is visible in the data. The post's own hedge
("more of a transition period than a clean comparison") was right, for a
different reason than it gave.

**Basis-specific, so state the basis.** "Pump prices consistently reacted
after about two weeks" and "correlation of 0.92" are both results on
*levels*. On week-over-week changes petrol's lag is 1 week and diesel's 3,
and correlations run about 0.2 lower. Neither figure is wrong; both need
"measured on price levels" attached.

**Contradicted by the current pipeline.** "Outside major shocks that
relationship mostly disappears… correlations ranged from weak to even
negative." The rebuild gives r = 0.96 for the 2020–2022 calm period. What
actually disappears in calm periods is the *identifiability of the lag* —
the winning lag wanders across 10 different values over 85 weeks — not the
correlation. A high calm-period correlation is usually a trend plateau
(`architecture.md`). Worth correcting explicitly, since it is the one claim
the current data contradicts outright.

## House style

- First person, opens from a concrete lived moment ("watching the news",
  "that was a pretty accurate description"), not from methodology.
- Body carries 3–5 bullets marked ✅ (findings) or 1️⃣2️⃣ (design decisions);
  ❓ introduces the question the post answers, 💡 the mental model.
- Every claim carries a number. Numbers are specific (0.92, NZ$0.40,
  NZ$306.60), never "significant" or "a lot".
- One honest limitation near the end, stated plainly — "a weekend data
  project rather than a controlled study", "still just a correlation" —
  followed by what would fix it.
- A surprise or reversal is the spine of the strongest posts: Part 3
  ("registration was supposed to be the boring part"), Part 4 (every test
  passed and the model was still wrong).
- Closing line is light, sometimes a joke (coffee ☕).
- Links to GitHub and sources go in the **first comment**, not the body.
  Part-to-part backlinks and 2–3 hashtags sit at the very bottom.
- Signed off as `NZ Fuel Price Project — Part N`.
- No point-forecast language on report measures — "if the pattern holds,
  we should begin seeing", never "will be". Matches the confidence-tier
  rule in `CLAUDE.md` / `architecture.md`.
