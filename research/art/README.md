# Post artwork

One-off generators for the Part 8 illustration. Not part of the weekly
chain — nothing here runs on a schedule, and nothing downstream depends on
it. Kept only so the published picture can be traced back to the data that
made it.

- `anim.py` — the animated GIF: 81 frames, one title card plus every month
  from Jan 2020 to Aug 2026. **Run from this directory**; it reads
  `fonts/*.ttf` and `../data/panel_weekly.csv` by relative path and writes
  the GIF beside itself.
- `gen.py` + `template.html` — the two static Sankeys and the companion
  page, published as an artifact (link in `docs/draft_part8.md`).
- `fonts/` — Archivo and IBM Plex, from the Google Fonts repo (OFL).
  Vendored because matplotlib's default DejaVu made the chart look like a
  lab plot.

`fuel_price_anatomy.gif` is committed rather than regenerated on demand:
it was built from weeks that MBIE still marks Provisional, so a rerun after
the June-quarter revision will not reproduce what was published.
