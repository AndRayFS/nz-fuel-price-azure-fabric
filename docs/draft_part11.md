# Part 11 draft — two castles

Status: **published 24 Sep 2026** — https://lnkd.in/p/eYUVXDe5. The text is
the owner's, in English; everything below it is the checking.

The posted text has **not** been re-read from LinkedIn, so any departure made
at posting time is unrecorded here. Part 9 had three such departures and they
were only found by reading the live post; worth doing once for this one too.

**Takes up the promise Part 9 made and Part 10 deferred.** Part 9 closed with
"the rebuilt weekly pipeline has to prove itself first — that is the next
post"; Part 10 went out on the margin instead. This post is the half that is
not code — why the rebuild was needed and what was decided. The implementation
is Part 12, and this post ends by saying so.

## The picture

`docs/images/castle2_layout.png`, **1080 × 1350** — a fairy-tale castle above,
a walking castle below, `PROJECT` and `REALITY` set in Archivo under each.
This is the only version kept: the generated source (a pencil diptych,
1774 × 887) was a scratch file and is not in the repository. The assembly —
each panel cropped around its own castle to 2:1, stacked, labels set — is a
few lines of PIL against the vendored font in `research/art/fonts/`.

**Why it had to be reassembled.** LinkedIn renders at most 4:5 and crops
anything taller. The source was 2:1 overall, so each panel was 4:1, which on a
phone is about 100 px tall. Downscaling to 400 px wide turned
both castles into grey smudges; the same test on the 1080 × 1350 assembly
reads clean, legs, spires, chimneys and all. Tone was the thing expected to
fail and did not: 4% of the source was darker than 64, and the line holds.

**On the two films.** Both are named in the text, and the drawing is
recognisably both of them. Covering the recognisable parts with the labels was
tried and rejected — the plates land on the spires and on the legs, which is
what the picture is for, and they hide only what someone unfamiliar would not
have spotted anyway. The mitigation that does work is the opposite: say it
first. Hence the credit line above the sign-off, which turns "that's Ghibli"
from a comment into a non-event.

## The post, 2,972 characters

In Part 2 of this series, I shared a beautiful architecture diagram: a mighty tree fed by data sources into Bronze, with a Silver trunk, Golden branches and reports as leaves — all held together by dbt.

Beautiful. Structured. Something to be proud of.

If you missed it: https://www.linkedin.com/posts/andreimor_tree-ugcPost-7487295986630025216-b4Rj/

That was eight weeks ago.

Any project looks like a perfect Disney castle when it is still on the presentation slide: symmetrical, flags in the wind, every tower exactly where it was designed to be.

Then production starts.

New modules appear, sometimes somewhere off to the side. Bugs get patched wherever they show up. Unexpected scripts grow like mushrooms. Some parts quietly stop being used — and nobody takes them down, so you keep heating rooms no one walks into.

After a while, you may end up with Howl's Moving Castle: smoking, slightly crooked, walking around on its strange little legs.

And here is the important part:

It still moves.

That ridiculous castle does its job every day.

The beautiful castle is just a drawing.

But it is a good idea to stop it occasionally and look inside.

I did. Three things immediately stood out:

1. Four out of five Gold-layer tables were no longer being used.
The new model calculation had moved to Python, but the old tables were still being refreshed, consuming time and resources.

2. Data was scattered across three places: the cloud database, my laptop and Git.
The Python scripts wrote CSVs, I committed them, and dbt loaded them into the database. Git had quietly become part of the data path.

3. The check against an outside source lived on my laptop.
We added it the day after a load quietly brought in week-old data and passed every test. It read an exported CSV and ran only after the data had already been loaded into the database. Potentially bad data could get inside first, and we checked it afterwards.

All of this was a symptom of the same thing.

The project had evolved, and two separate worlds had grown inside it: the weekly production pipeline and the research environment. The two began leaking into each other.

Time for a refactor.

So the rebuild has three rules:

1. The main data pipeline lives in the cloud and runs automatically on a schedule. No laptop, no manual start for the main process and intermediate steps. Execution is monitored by email.
2. The database is the single source of truth. The laptop only receives data needed for research. Git holds configuration and code, not datasets.
3. Validation against external sources happens before the data is loaded, not afterwards.

How I built this — and what survived the refactor — in the next post.

Which of the two castles are you living in right now?

Drawings: AI, with apologies to Disney and Studio Ghibli.

Previous post — Part 10, the rise that already happened: https://lnkd.in/p/e_6iddd2

NZ Fuel Price Project — Part 11 ☕

#DataEngineering #NewZealand #DataAnalytics

## Numbers, and where each came from

Three numbers and one incident, which is all a post at this altitude can
carry.

- **"Eight weeks ago."** Part 2 was published 27 Jul 2026, decoded from its
  LinkedIn post id; this drafts on 20 Sep 2026.
- **"Four out of five Gold-layer tables."** `lag_correlation`, `lag_resolved`,
  `factor_volatility` and `volatility_config` were deleted 8 Sep 2026, leaving
  `forecast_accuracy`. Until then `dbt run --full-refresh` rebuilt all five
  every week, which is the "consuming time and resources" in the post.
- **"Three places."** The warehouse; `data/*.csv` on the laptop; and
  `seeds/period_flags.csv` and `seeds/forecast_history.csv` in git until
  `6ab239d` on 7 Sep 2026. The two seeds that remain — `periods.csv` and
  `variable_mapping.csv` — are configuration, which is what makes rule 2
  something the project already half-follows.
- **"The day after a load quietly brought in week-old data."** The incident is
  19 Aug 2026: `ingest_mbie_weekly` read the previous week's file from a CDN
  edge cache, reported `Succeeded`, and all 60 tests passed on it
  (`architecture.md`). `research/aip_check.py` was committed the next day,
  `5ef030d`, 20 Aug.
- **"It read an exported CSV and ran only after the data had already been
  loaded."** That script sat at step 4b, after the panel export, and read
  `data/panel_weekly.csv`. It also exited non-zero, so at that point it could
  stop the chain. Both facts are in `workstreams.md` W2 and in the commit.

## What the three rules claim, and what is actually built

Stated as rules in the present tense, which is true of all three; completion
is not uniform, and Part 12 is where that gets reported.

- **Rule 1 is built.** The Logic App `trigger-weekly-load` fires 09:07 Thursday
  NZ, dispatches the workflow, and mails on anything but success — deployed and
  proven 19 Sep 2026. The Power BI refresh is still manual, which is why the
  rule is scoped to "the main data pipeline" and its intermediate steps.
- **Rule 2 is half built.** The two data seeds left git on 7 Sep; research's
  own read path out of the warehouse is W15 and is not written yet.
- **Rule 3 is decided, not built.** Collection already runs before silver
  (step 1); the comparison is `monitor_aip_gap`, built by the same `dbt run`
  as silver. Moving it forward is the work. **The post deliberately does not
  promise it the right to stop the load** — that authority was taken away on
  purpose on 22 Aug 2026 and giving it back is a separate decision nobody has
  made.

## Corrections made to the owner's text before this version

Each was checked against the repository rather than against memory.

- **Git was not a leftover, it was a leg of the journey.** "CSV files were left
  in the repository" became "the Python scripts wrote CSVs, I committed them,
  and dbt loaded them into the database" — which is what `6ab239d`'s commit
  message describes.
- **The leaking had a direction, and it was the other one.** "Changes made for
  research began affecting the regular data pipeline" was reversed: the
  documented case is a pipeline path change breaking research scripts. The
  sentence is now neutral — "the two began leaking into each other" — which
  covers both and overstates neither.
- **"Data validation" was too wide.** Form tests on silver run where they
  should; what lived on the laptop was the check against an *outside* source.
  Narrowed, which also lines it up with rule 3.
- **The castle metaphor contradicted finding 1.** "Blocks get neglected and
  eventually collapse" was replaced with "nobody takes them down, so you keep
  heating rooms no one walks into" — dead tables did not collapse, they kept
  being rebuilt, which is the point of finding 1.
- **Future tense became present.** "So I am changing three things" is now "So
  the rebuild has three rules", because the trigger is already deployed and
  Part 12 would otherwise open by contradicting this one.

## Deliberate departures from the series' house style

This post is looser than Parts 7–10, on the owner's call.

- **No obligatory honest-limitation bullet.** An earlier draft carried "none of
  this found a new fact about fuel prices". That is not a limitation of a
  refactor, it is a description of what a refactor is.
- **Three numbers, no more.** Everything below that altitude — model names,
  schemas, step numbers, service names — is Part 12's material.
- **The closing question is left open**, without the second half asking whether
  anyone has ever worked on the tidy castle. That half nudges toward "no" and
  risks reading as "who here still believes in a perfect world". Open invites
  an answer either way.
- **Links.** Part 2's backlink sits in the body, high, because it is load
  bearing — the post is about that diagram. Repository and report links, if
  any, go in the first comment as usual.
