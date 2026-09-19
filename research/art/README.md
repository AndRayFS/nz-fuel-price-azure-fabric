# Post artwork

One-off generators for the pictures that went out with the LinkedIn series —
Part 8's anatomy of a litre, Part 9's forecast lines, Part 10's margin. Not
part of the weekly chain: nothing here runs on a schedule and nothing
downstream depends on it. Kept only so a published picture can be traced back
to the data that made it.

Every script reads `fonts/*.ttf` by relative path, so **run them from this
directory**. Each writes its PNG beside itself, and the PNGs are committed —
they were built from weeks MBIE may still revise, so a rerun need not
reproduce what was published.

- `anim.py` — Part 8, the animated GIF: 81 frames, one title card plus every
  month from Jan 2020 to Aug 2026, off `../data/panel_weekly.csv`.
- `gen.py` + `template.html` — the two static Sankeys and the companion
  page, published as an artifact (link in `docs/draft_part8.md`).
- `nowcast_levels.py`, `nowcast_chart.py` — Part 9. What the pump did against
  what the model called two weeks earlier, and the running sum of absolute
  error through 2026. Both read `../data/nowcast_results.csv`, written by
  `research/nowcast_in_adl.py --save`.
- `margin_pipe.py` — Part 10, the one that was published. The importer margin
  as a band centred on zero whose full thickness is the margin in c/L, so a
  halved margin is a pipe that visibly halves. Red where it went below zero;
  no y ticks, because each edge sits at half the margin and a tick read as
  the margin would halve every number on the chart.
- `margin_gap.py` — Part 10, the alternative that was not used. Pump price
  against the break-even (landed cost, excise and ETS, plus GST), so the gap
  between the lines is the same margin told as a difference. Correct, and it
  asks the reader to measure that difference by eye at the bottom of a
  400 c/L axis.
- `fonts/` — Archivo and IBM Plex, from the Google Fonts repo (OFL).
  Vendored because matplotlib's default DejaVu made the chart look like a
  lab plot.

`fuel_price_anatomy.gif` is the clearest case of why the output is committed
and not regenerated on demand: it was built from weeks MBIE still marks
Provisional, so a rerun after the June-quarter revision does not reproduce
what was published.
