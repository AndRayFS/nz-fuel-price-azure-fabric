# Part 10 draft — the rise that already happened

Status: **published 19 Sep 2026** — https://lnkd.in/p/e_6iddd2. Drafted in
Russian at the owner's request, then translated and cut to house length. One
image attached, the margin pipe; hashtags
`#FuelPrices #NewZealand #DataAnalytics`; no links in the first comment, for
the reason under "Notes on choices".

**Takes over Part 9's promise, deliberately.** Part 9 ended "Not in the report
yet: the rebuilt weekly pipeline has to prove itself first. That is the next
post." The pipeline has not had a quiet fortnight to prove anything in —
prices moved instead, and the data became more interesting than the plumbing.
The post says so in its first line rather than letting a reader notice the
promise was skipped. The pipeline post keeps its place, one behind.

Numbers: `docs/research.md`, "What the record says after a margin compression"
and "The nowcast's Brent is futures". Panel exported 19 Sep; MBIE's latest
week is 11 Sep. Chart: `research/art/margin_pipe.py` ->
`margin_pipe_2026.png`.

## The picture

`research/art/margin_pipe.py` -> `margin_pipe_2026.png`. Petrol and diesel
from January 2025. The band's full thickness is the importer margin in c/L,
GST included; the dashed outline is its own trailing two-year mean. It pinches
almost shut in March, again in late July, and is pinched now. Where it crosses
itself the margin was negative.

`research/art/margin_gap.py` -> `margin_gap_2026.png` is the alternative: pump
price against break-even, same story told as a gap rather than a width. The
pipe is the one that needs no arithmetic from the reader.

## The draft, 2,805 characters

Last time I said the next post would be the rebuilt weekly pipeline, once it
had proved itself. It hasn't had the chance — prices moved first, and the data
got more interesting than the plumbing. Substance now, pipeline next.

Regular 91 hit $3.25/litre last week, diesel $2.96 — up 25 cents in a month,
the highest since late May. The Strait of Hormuz is closed, a Saudi pipeline
is down after drone attacks, crude is back above US$100, and the AA says it
may not ease before mid-November.

That's all in the news. Here's the part that isn't.

❓ How much of the rise is still ahead of us?

Most of it has already happened — just not at the pump yet.

✅ Between 28 August and 11 September the importer's calculated cost rose
26 c/L for petrol and 24 c/L for diesel. The pump price rose 4 cents. About a
sixth of it reached us.

✅ The rest is sitting in the importer's margin: 16 c/L for petrol against a
usual 45, and 24 c/L for diesel against 53. That's roughly 29 cents a litre
already inside the system and not yet at the pump.

✅ Gaps like this don't tend to last. Over 15 years retail has closed about
half of one within six weeks, three quarters within three months.

💡 The margin isn't the story — it's the instrument. Cost and tax are buried
inside the pump price; the margin is how you see the gap.

So which way does the gap close? Both ways happened this year.

✅ End of July: diesel's margin was tighter than it is now. Over the next
month the calculated cost barely moved, 187.5 to 187.7 c/L. The pump rose 18
cents, and almost all of that went into rebuilding the margin.

✅ April: the margin went below zero — diesel selling under its calculated
cost. The pump kept rising for two weeks anyway, then crude collapsed, costs
fell about 100 c/L, and the pump turned down. The margin then hit its highest
in 22 years. Same mechanism, reversed.

The difference wasn't the margin. It was what the cost did — and that's oil.

⚠️ I can't call oil, and I can show why. Every day since 1987 when Brent fell
more than 5% — 196 of them. A month later oil was higher in 48% of cases,
against 54% after an ordinary day. The median doesn't move. The standard
deviation of outcomes more than doubles. A sharp move raises uncertainty
rather than setting direction.

⚠️ September's MBIE figures are provisional and will be revised after the
quarterly CPI. And some of the compression is an artefact: MBIE uses the
week's average price, not the actual purchase price, so the difference lands
in the margin.

So the next increase isn't news from the future. It's an echo of something
that already happened. The open question isn't whether prices rise over the
next few weeks — it's whether they hold afterwards.

MBIE weekly data since 2004; daily Brent from FRED since 1987.

NZ Fuel Price Project — Part 10 ☕

## Corrections made to the Russian draft before translating

Four, all found by checking the text against the scripts rather than against
memory.

- **"Fuel prices were higher a month later" was wrong** — the Brent study
  measures where *oil* went, not the pump. Nothing in this project has
  measured the pump a month after a crude crash. Fixed to "oil was higher".
- **137 events is the count at −5.77%, not −5%.** The round threshold gives
  196 days, and the conclusion is identical (48% against 54%), so the post
  takes the round number and the larger sample.
- **"The range of outcomes roughly doubles" was half true.** At one month the
  interquartile range widens about 20%; the standard deviation goes up 2.1x.
  What doubles is the tails, so the post names the standard deviation.
- **"Almost exactly rebuilding the margin" overstated July.** The pump rose
  17.9 c/L and the margin 16.1, so almost all of the rise went into margin —
  but the margin reached 29.6 against a norm of 46.7, two thirds of the way
  back, not all of it. The sentence now says where the money went, not that
  the margin was restored.

## Notes on choices

- **The conclusion sits in the middle, not at the end.** "Most of it has
  already happened" is the fourth paragraph. A reader who stops halfway still
  leaves with the finding; the uncertainty section is positioned after the
  answer rather than instead of one.
- **The margin is demoted to an instrument, in one bullet.** An earlier draft
  built the whole post around it, which is a mistake: a driver does not care
  what an importer keeps. The margin earns its place only because cost and tax
  are invisible inside a pump price.
- **Two worked examples, both from this year, both checkable on the chart.**
  The original plan was to compare against history. That was abandoned after
  the record turned out not to support it — see `research.md`, "What the
  record says after a margin compression": with pre-2010 data excluded and the
  benchmark required to sit inside one era, there is no usable precedent for
  petrol at this depth. July and April are in-era and eight and twenty weeks
  old.
- **No point-forecast language**, per the house rule. "Most of it has already
  happened" is a statement about the present; every forward sentence is
  conditional.
- **Mixed GST bases, knowingly.** The cost figures (+26, +24) are ex-GST and
  the pump figures (+4) include it. Like for like the cost rise is 30 c/L at
  the pump and the share passed through is 15% rather than 17% — still "about
  a sixth". Correcting it would cost a paragraph explaining GST and change no
  conclusion.
- **No links this time.** Earlier parts put GitHub and the public report in
  the first comment. This post is about the fuel market rather than the build,
  and a repository link invites the reader to check the plumbing instead of the
  claim. The next post, which is the pipeline, is where they belong again.
- **Hashtags:** `#FuelPrices #NewZealand #DataAnalytics`. The series has run
  `#Forecasting #NewZealand #DataAnalytics` since Part 9. `#Forecasting` is
  dropped here and only here: this post's spine is that the near-term rise has
  already happened and that oil cannot be called, so the tag would promise the
  one thing the text declines to do.
