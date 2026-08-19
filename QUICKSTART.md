# Working with this project — quick reference

## Start of every session

```bash
cd ~/nz-fuel-price-project
source .venv/bin/activate
cd nz_fuel_price_project
```

Confirm it worked:
```bash
dbt --version
```
Should show `fabric` as a registered adapter, and the prompt should show
`(.venv)` at the start of the line.

**Before running anything that touches the Warehouse:** make sure the
Fabric capacity is resumed (Azure Portal → `nzfuelcapacity` → Resume). It
auto-pauses nightly at 00:01 NZT regardless of state — check Logic App run
history occasionally (not daily) to confirm it's still firing correctly.

## Common commands

| Task | Command |
|---|---|
| See compiled SQL before running (check Jinja substituted correctly) | `dbt compile --select <model>` |
| View compiled file | `cat target/compiled/nz_fuel_price_project/models/<path>/<model>.sql` |
| Run one model | `dbt run --select <model>` |
| **Weekly data refresh (IMPORTANT)** | Always use `--full-refresh` — plain `dbt run` has been observed to not reliably pick up new bronze rows for these models. `dbt run --select silver_general silver_fuel lag_correlation lag_resolved factor_volatility --full-refresh` |
| Run one model, force full rebuild (needed after changing materialization or column structure) | `dbt run --select <model> --full-refresh` |
| Run + tests together | `dbt build --select <model>` |
| Preview output without leaving terminal | `dbt show --select <model> --limit 10` |
| Run all tests | `dbt test` |
| Reload seed data (e.g. after editing periods.csv or variable_mapping.csv) | `dbt seed --select <seed_name>` |
| Reload seed after changing its *columns* (not just values) | `dbt seed --select <seed_name> --full-refresh` |
| Update Provisional→Final revision history | `dbt snapshot` |
| Regenerate docs + lineage graph | `dbt docs generate` then `dbt docs serve --port 8081` |
| Run a one-off macro (e.g. diagnostic) | `dbt run-operation <macro_name>` |

## Weekly data update — the full chain, in order

MBIE publishes on Wednesdays. This is the whole sequence; skipping a step
leaves Report 1 showing last week's numbers with this week's date.

```bash
source /Users/Ray/nz-fuel-price-project/.venv/bin/activate

# 0. resume the capacity, run `ingest_mbie_weekly`, and CHECK ITS ROW COUNT
#    (see below) before trusting anything downstream
dbt snapshot                                         # 1. revision history
dbt run --full-refresh                               # 2. bronze -> silver/gold
dbt test                                             # 3. 60 tests, all should pass
python research/export_panel.py                      # 4. panel out to CSV
python research/build_period_flags.py                # 5. regime axes, from the panel
python research/backtest.py                          # 6. refit + forecasts
dbt seed --select period_flags forecast_history --full-refresh   # 7. -> warehouse
dbt run --select forecast_accuracy --full-refresh    # 8. rebuild the report table
```

Then refresh the Power BI dataset.

Notes:

- **Check `rowsRead` on the copy activity, not just its status.** On
  19 Aug 2026 the ingest reported `Succeeded` twice while serving a
  week-old file out of MBIE's CDN — green pipeline, 60 green tests, report
  a week stale. The pipeline now appends a per-run cache-buster to the URL;
  the row count is still the only proof the fetch was fresh. Full account
  in `docs/architecture.md`.
- **Step 5 comes before step 6, not after.** `build_period_flags.py` reads
  the panel and `backtest.py` reads the flags, so running the flags later
  leaves `backtest_results.csv` split on last week's regime values. The
  centred 9-week window means the last four weeks' numbers move every time
  a new week lands, so this is not a no-op.
- **`--full-refresh` everywhere**, per the rule at the top of this file.
  Step 7 especially: a plain `dbt seed` loads into the existing table and
  fails the moment a column is added.
- Steps 1, 2, 3, 4, 7 and 8 need the capacity running. Steps 5 and 6 are
  local.
- Provisional weeks are handled automatically: `backtest.py` trains only on
  Final rows and applies the model to every week, so the series extends by
  itself as MBIE finalises. Nothing to adjust by hand.
- Whole chain is about five minutes.
- `seeds/brent_daily.csv` (FRED `DCOILBRENTEU`) is diagnostic only — no
  model or forecast reads it. FRED runs a few days behind, so the newest
  week's `brent_mean` is an average of whatever days exist.

**This wants automating and moving off the laptop.** It is eight manual
steps with a hard dependency on one person's venv, one machine's Azure
login and the capacity being awake. Tracked as a separate task, not
solved here.

## Project structure

- `models/silver/` — long→wide pivots (`silver_general`, `silver_fuel`)
- `models/gold/` — lag correlation + resolved + volatility
- `seeds/periods.csv`, `seeds/variable_mapping.csv`
- `snapshots/mbie_revisions.sql`
- `macros/pivot_variables.sql`, `macros/lag_correlation_series.sql`

Full design rationale: `docs/architecture.md`
Source (MBIE) structure and gotchas: `docs/mbie_notes.md`

## dbt vars (dbt_project.yml)

- `volatility_window_weeks` — rolling window size for the volatility
  indicator (currently 6). Change here, not in SQL, then
  `dbt run --select factor_volatility`.

## After making changes

```bash
git add <files>
git commit -m "..."
git push
```

Repo: https://github.com/AndRayFS/nz-fuel-price-azure-fabric

## If something feels broken

1. `dbt debug` — checks connection to Warehouse specifically
2. Check capacity isn't paused (Azure Portal)
3. Check you're in the venv (`(.venv)` in prompt) and in the
  `nz_fuel_price_project` folder, not one level up
