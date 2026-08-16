# Part 7 draft — the report that shows its own losses

Status: draft for the user to polish and publish, alongside the redesigned
Report 1. Written 17 Aug 2026.

Spine: the formula already published in Report 1 lost to "the price won't
change", and could never have been backtested in the first place. The
replacement wins, and the report now says by how much — including the weeks
it loses.

House style, hashtag conventions and the correction log: `linkedin_series.md`.
Part 6 closed promising "back to the data: new sources, and extending the
methodology", which this post delivers.

## Deliberately held back for Part 8

Each of these is its own story and does not fit in 2,500 characters:

1. **"The crisis turned out to be a publication status."** Nineteen weeks
   from Apr 2026 sit as Provisional; training on them flips which fuel
   appears to pass costs through faster. MBIE's own pages confirmed it.
2. **"Everyone says prices follow oil. Oil barely moved."** Crude +10.1%
   against diesel's landed cost +61.4%, 27 Feb – 7 Aug 2026. This is the
   one the closing line teases, and the strongest candidate for Part 8 —
   it reads without any prior context.
3. **"How the method fooled itself": 2.22 → 1.00.** Separate per-lag
   regressions had neighbouring weeks each claiming the same market move.
   Kept inside Part 7 only as the two-line "never more than in full" claim.

## Fact-check trail

Every number below was recomputed on 17 Aug 2026 before this draft was
fixed. Sources: `research/backtest.py` output (`data/backtest_results.csv`)
and a fresh ADL fit on `data/panel_weekly.csv`, Final rows only, 2010+.

| claim in the post | verified value |
|---|---|
| MAE 1 week, petrol | 1.61 model vs 2.22 naive |
| MAE 3 weeks, petrol | 4.67 model vs 5.58 naive |
| edge 27% → 16% | h=1 27.5%, h=2 21.7%, h=3 16.3% |
| loses four weeks in ten | beats naive in 61.6% of weeks (h=1) |
| lag shares 26/39/20/9 | petrol 26.3 / 39.0 / 19.6 / 8.8, sums to 1.004 |
| backtest window | 706 forecasts per fuel, 1 Feb 2013 – 7 Aug 2026 |
| crude +10.1%, diesel cost +61.4% | 27 Feb → 7 Aug 2026, exact |

**Every figure above is provisional in one specific way, and it must be
rechecked once this year's weeks finalise.** The 19 weeks from 3 Apr to
7 Aug 2026 are still `Provisional`: MBIE suspended `Importer cost` and
`Importer margin` on 18 Mar, backfilled them, and the whole row stays
Provisional until Stats NZ publishes the quarter's CPI. Which numbers move,
and how:

| figure | exposure to the revision |
|---|---|
| MAE, skill, "four weeks in ten" | **Direct.** The model trains on Final only but is scored on every week with a known outcome, 2026 included. |
| crude +10.1%, diesel cost +61.4% | **Direct.** 27 Feb is Final; 7 Aug is Provisional, and `Importer cost` is one of the two suspended series. |
| lag shares 26/39/20/9 | **Indirect.** Fitted on Final rows only, so today's value is clean — but 19 new Final weeks will shift it. |
| backtest window | End date moves with each refresh. |

The target itself is solid: `adjusted_retail_price` has never been revised
in 1,164 weeks. What moves is the cost side, by roughly 0.5 c/L, against a
model MAE of 2.7 — so the ranking of methods should hold and the shares
should barely move. Should. That is a prediction, not a measurement, and it
is exactly what the recheck is for.

**When to recheck:** after Stats NZ publishes the June-quarter CPI. Re-run
`research/export_panel.py`, then `headline_results.py` and `backtest.py`,
and diff against this table. If a headline number moves outside its stated
precision, the post needs a correction comment — the series convention is
to correct in comments and leave the body standing (`linkedin_series.md`).

**Three traps this draft had to be pulled out of**, all worth remembering
before the next post:

- The lag shares are **cost**-driven, not crude-driven. Calling them
  crude-driven contradicts the post's own closing line.
- "The spread of errors roughly triples" holds for sharp **landed cost**
  moves (3.4x petrol, 2.4x diesel). Keyed to **crude** volatility instead —
  which is what the report actually shades — the ratio is only 1.8 / 1.7.
- Forecasts start Feb 2013, not 2010. The first three years are training.

## The draft, 2,545 characters

```
I built a forecast into my fuel price report.

Then I tested it properly, and it lost to a rule a child could follow:

"The price won't change."

Not the new model. The old one I'd already published.

❓ How do you know a forecast is any good?

Not from the history you fitted it to.

So I took March 2018, deleted everything after it, trained the model, forecast two weeks ahead, waited for the actual data, and compared the result.

Then repeated that for every week from February 2013, using data going back to 2010.

Seven hundred honest exams.

✅ My published formula failed.

It picked its lag from the "current period" — but periods themselves can only be identified after the fact. That 28 February 2026 marked the beginning of a crisis wasn't knowable until weeks later.

A method that needs hindsight to run cannot be backtested.

That's not a bug I fixed. It's a design I retired.

✅ The replacement wins — and I can quantify by how much.

Mean absolute error one week out: 1.6 c/L, versus 2.2 c/L for simply assuming the price won't change.

Three weeks out: 4.7 c/L versus 5.6 c/L.

The edge falls from 27% to 16% as the forecast horizon stretches — exactly what I'd expect. If it didn't, I'd be looking for data leakage.

✅ It still loses to "no change" four weeks out of ten.

The advantage isn't consistency. It's missing by less when the big moves happen.

The model also distributes the cost-driven movement across time: 26% in the same week, 39% the next, then 20%, then 9%. By week six the cumulative response reaches 1.00 — costs arrive in full, and never more than in full.

💡 The model doesn't predict oil.

It asks what has already happened to costs that hasn't reached the pump yet.

⚠️ When landed costs move sharply, the model degrades badly — the spread of its errors roughly triples.

But so does "no change".

In a storm, the underlying relationship itself becomes harder to predict. The report shades those periods rather than hiding them.

There's another correction to my earlier posts.

I said pump prices react "after about two weeks".

Too tidy.

The strongest response is around week one, most of it has arrived by week three, and petrol responds faster than diesel.

The report now carries its own scorecard: what it predicted, what actually happened, and whether it beat doing nothing.

Every week.

Including the ones it lost.

Less comfortable than a clean line. Also the only version worth trusting.

Next: everyone says fuel prices follow oil.

From 27 February to 7 August, crude rose 10.1%, while the landed cost of diesel rose 61.4%.

So what actually moved it?

NZ Fuel Price Project — Part 7 ☕

#DataAnalytics #Forecasting #PowerBI #NewZealand
```

If the 2,500 limit is strict, the cheapest cut is the 2013 line, down to
`Then repeated that for every week since February 2013.` — 33 characters,
and the claim stays true.

## Notes on choices

- `#DataEngineering` and `#dbt` dropped for this post only: it is about
  model validation, and neither the pipeline nor dbt appears in the text.
  They belong back on a post that is actually about the stack.
- Links to GitHub and to the report go in the **first comment**, per the
  series convention — not in the body.
- No point-forecast language: "what has already happened that hasn't
  reached the pump yet", never "will be". Matches `CLAUDE.md`.
- The correction on "about two weeks" is in the body rather than a
  comment, because the reversal is the story the series is telling.
