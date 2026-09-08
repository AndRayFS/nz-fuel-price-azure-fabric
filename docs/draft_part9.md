# Part 9 draft — the week the model could not see

Status: **published 8 Sep 2026** — https://lnkd.in/p/eNTj-JMQ. Drafted in
Russian at the owner's request, then shortened and translated; the English
text below is what went out, apart from three edits made at posting time:
"my model" for "the model", "the PowerBI report" for "the report", and a
backlink to Part 8 above the sign-off. One image attached, the petrol and
diesel price chart. No hashtags, against the house style's 2-3.

Both ordering questions resolved at posting time. Part 8 went out first and
Part 9 links back to it. The condition in `draft_part8.md` — that Part 9 wait
until the nowcast is implemented in `pipeline/backtest.py` — was relaxed
deliberately: it is measured and validated but not implemented, and the post
says so in its own body rather than implying a live feature.

Numbers: `docs/research.md`, "The week in progress is partly visible" and
"The nowcast survives the walk-forward test". Chart:
`research/art/nowcast_chart.py` -> `nowcast_error_2026.png`.

## The pictures

Two, and they carry the limitation the text only names.

`research/art/nowcast_levels.py` -> `nowcast_levels_2026.png`. Petrol and
diesel through 2026, two weeks ahead, in c/L: what the price did, what the
model called, what the corrected model called. Each forecast is plotted on the
week it was a call **for**, not the week it was made. It shows the gain and it
shows March, where neither version came close.

`research/art/nowcast_chart.py` -> `nowcast_error_2026.png`. Running sum of
absolute errors through 2026: one line through the quiet weeks, parting from 6
February. Optional second image if one is not enough.

## The draft, ~1,300 characters

MBIE publishes fuel prices once a week, on Wednesdays, for the week that ended
on Sunday. The model forecasts one, two or three weeks ahead — and the first
of those weeks is already under way, with no data for it yet.

Something about it is knowable anyway. MBIE's importer cost tracks Singapore
fuel prices and the exchange rate. Those quotes are paid data, but crude and
currency trade every day while MBIE waits for Wednesday.

✅ I took the week's first three days from Brent, converted them to NZ dollars,
and gave them to the model.

✅ Average error fell 13% two weeks ahead, 12% at three, 7% at one. Across 707
weeks since 2013, refit every week on data up to that week only.

✅ Largest in a crisis: when the price moves 5–20 c/L over a fortnight, the
model used to miss two thirds of the move, now about half.

Not a silver bullet, and the charts show why:

⚠️ In calm weeks it changes nothing — sometimes tenths of a cent worse.

⚠️ Nothing saw March 2026 coming. Petrol rose 95 c/L, diesel nearly 200. The
corrected model turned a week earlier and ran 6–7 c/L closer; both were still
far behind.

⚠️ In the six sharpest weeks of the year the gain nearly vanishes.

Not a prediction of the future — information that already exists, arriving
earlier than the report.

Not in the report yet: the rebuilt weekly pipeline has to prove itself first.
That is the next post.

NZ Fuel Price Project — Part 9

## Notes on choices

- **The limitations are three bullets, not one apologetic sentence.** The
  charts show them anyway; naming them first is cheaper than being corrected
  in the comments.
- **"Not a silver bullet" is the spine.** The earlier draft led with 19% in
  the top decile of weeks, which was true and misleading: that decile spans
  moves from 8 to 56 c/L, so one number covered wildly different weeks. The
  5–20 c/L band with "two thirds of the move, now half" says the same thing
  without the bucket doing the work.
- **13%, not 13.9%**, and no second decimal anywhere: rounding down is the
  cheapest defence against a reader who recomputes.
- **All three horizons are quoted, not just the best one.** The post names
  one, two and three weeks, so giving only the two-week figure — the largest
  of the three — would read as picking. One week gains least (7-8%) because
  the forecast is cumulative: the correction enters once at h=1 and twice at
  h=2, so more of the response is recovered the further out the horizon runs,
  until accumulated error overtakes it at three weeks.
- **"The week's first three days" says three inside the sentence.** An earlier
  cut removed the line that introduced them and left "those three days"
  pointing at nothing.
- **No point-forecast language**, per the house rule. "Использование
  информации, которая уже существует" is the whole claim.
- Numbers: `docs/research.md`, "The week in progress is partly visible" and
  "The nowcast survives the walk-forward test". The 95 and ~200 c/L climbs
  are 20 Feb to 10 Apr (petrol, 252 -> 347) and 20 Feb to 17 Apr (diesel,
  187 -> 381).
- Links to GitHub and the public report go in the **first comment**.
