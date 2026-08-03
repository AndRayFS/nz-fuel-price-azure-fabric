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
| Run one model, force full rebuild (needed after changing materialization or column structure) | `dbt run --select <model> --full-refresh` |
| Run + tests together | `dbt build --select <model>` |
| Preview output without leaving terminal | `dbt show --select <model> --limit 10` |
| Run all tests | `dbt test` |
| Reload seed data (e.g. after editing periods.csv or variable_mapping.csv) | `dbt seed --select <seed_name>` |
| Reload seed after changing its *columns* (not just values) | `dbt seed --select <seed_name> --full-refresh` |
| Update Provisional→Final revision history | `dbt snapshot` |
| Regenerate docs + lineage graph | `dbt docs generate` then `dbt docs serve --port 8081` |
| Run a one-off macro (e.g. diagnostic) | `dbt run-operation <macro_name>` |

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
