# `research/` — estimation code, deliberately outside the dbt pipeline

`analyses/` holds dbt SQL analyses that compile against the warehouse.
This directory holds Python that does what SQL cannot: joint regression
across many lags at once (ADL/ECM), with autocorrelation-robust standard
errors.

**Division of labour.** dbt and the Fabric warehouse remain the source of
truth for *data*. Python only *estimates*. Results go back into `docs/`;
if a fitted quantity ever needs to reach Power BI it returns as a seed,
the way `brent_daily` did.

**Everything runs offline.** `export_panel.py` pulls the weekly panel once
into `data/panel_weekly.csv` (committed). After that no Azure is needed —
which matters because estimation is a loop of twenty specifications, the
F2 capacity auto-pauses at 23:00 NZT, and from 28 Aug 2026 it bills real
money.

```bash
source /Users/Ray/nz-fuel-price-project/.venv/bin/activate
python research/export_panel.py    # only when the warehouse has new weeks
```

## Data notes that constrain what can be fitted here

- **Use 2010+ at the earliest.** The published components do not reconcile
  before 2010: `adjusted_retail − taxes − gst − ets − importer_cost −
  importer_margin` is exactly 0 in every row from 2010, but reaches 13.8
  c/L in 2004–2009 (`docs/mbie_notes.md`).
- **Prefer the import era (Apr 2022+)** for pass-through work: ~228 weeks
  per fuel, one retail source, no domestic refinery.
- **Fit on changes, not levels** — both series trend, and the level of
  `importer_margin` has tripled since 2004.
- **`period_id` is null for 964 of 1,164 weeks.** `periods.csv` marks named
  episodes only; unlabelled weeks are not "unknown", they are ordinary
  weeks. Decide explicitly how they are treated before any crisis/calm
  comparison. **Superseded by `seeds/period_flags.csv`** — proposed, not yet
  merged — which gives all 1,164 weeks a value on nine independent axes
  instead of one crisis/calm label. **Filter on `data_status = 'final'`
  before estimating anything**: the 19 Provisional weeks from Apr 2026 are
  enough on their own to invert which fuel appears to respond faster. Rationale, tests and what was discarded:
  `docs/period_labelling.md`. Regenerate with:

  ```bash
  python research/build_period_flags.py   # derived; hand edits get overwritten
  ```
