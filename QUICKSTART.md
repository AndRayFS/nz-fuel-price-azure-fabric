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
Fabric capacity is resumed (Azure Portal → `nzfuelcapacity` → Resume). There
is no auto-resume — it was disabled deliberately — so this is always a manual
step. It auto-pauses nightly at **23:00 NZT** regardless of state; check Logic
App run history occasionally (not daily) to confirm it's still firing
correctly.

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
| **Is there anything to run this week?** | `python pipeline/gate.py` — exit 0 go, 2 nothing to do, 1 stop and look |
| Check the gate's logic without touching Fabric | `python pipeline/test_gate.py` |
| Read this week's signals only | `dbt test --select monitoring` |
| What changed under us in the last snapshot run | `dbt show --select monitor_revision_summary --limit 20` |
| Regenerate docs + lineage graph | `dbt docs generate` then `dbt docs serve --port 8081` |
| Run a one-off macro (e.g. diagnostic) | `dbt run-operation <macro_name>` |

## Weekly data update — the full chain, in order

MBIE publishes on Wednesdays. This is the whole sequence; skipping a step
leaves Report 1 showing last week's numbers with this week's date.

```bash
source /Users/Ray/nz-fuel-price-project/.venv/bin/activate

# 0. resume the capacity and run `ingest_mbie_weekly`
python pipeline/gate.py                              # 0b. THE GATE — stop here unless it says 0
python research/aip_check.py                         # 1. collect the AIP weeks
dbt seed --select aip_singapore_weekly --full-refresh  # 1b. -> monitoring schema
dbt snapshot                                         # 2. revision history
dbt run --full-refresh                               # 3. bronze -> silver/gold/monitoring
dbt test                                             # 4. everything outside `monitoring`
                                                     #    must pass; monitoring warns
python research/export_panel.py                      # 5. panel out to CSV
python research/build_period_flags.py                # 6. regime axes, from the panel
python research/backtest.py                          # 7. refit + forecasts
dbt seed --select period_flags forecast_history --full-refresh   # 8. -> warehouse
dbt run --select forecast_accuracy --full-refresh    # 9. rebuild the report table
python pipeline/mark_processed.py                    # 10. close the run
```

Then refresh the Power BI dataset.

Notes:

- **Step 0b is the only step allowed to stop the run, and its exit code is
  the whole point.** `0` carry on, `2` nothing to do (stop, quietly), `1` stop
  and go and look. **It cannot stop anything by itself** — this block is a
  list of commands, not a script: there is no `set -e` and no dependency
  between the steps, so pasting the whole thing on a `nothing_new` week runs
  the entire chain on unchanged data. Run step 0b on its own, read what it
  says, and only then continue. Binding the chain to the verdict is W7.
- **On `nothing_new`, check MBIE by hand before anything else.** Open
  `https://www.mbie.govt.nz/assets/Data-Files/Energy/Weekly-fuel-price-monitoring/weekly-table.csv`
  **in a browser** — scripts get an Imperva challenge, browsers get the file
  (`docs/mbie_notes.md`) — and read the date on the last line. Newer than
  `bronze_week`? MBIE published and the CDN served us a stale copy: re-run
  `ingest_mbie_weekly` and go back to step 0b. Same week? Nothing has been
  published yet and there is genuinely nothing to do. This costs ten seconds
  and no capacity, and it is the independent read W3 wanted — the browser
  reaches a New Zealand edge, the copy activity an Australian one, and their
  disagreement is exactly what made 19 Aug visible. The AIP route below
  answers the same question without a browser, but needs the capacity up. It reads `rowsRead` off the copy activity through the
  Fabric REST API — the number a human used to read in the portal — and
  compares it against bronze and against what the source held when the last
  week was processed. On 19 Aug 2026 the ingest reported `Succeeded` twice
  while serving a week-old file out of MBIE's CDN: green pipeline, 60 green
  tests, report a week stale. The gate returns `2` on that run and the chain
  never starts. Reasoning in `pipeline/gate.py`; full account of the failure
  in `docs/architecture.md`.
- **Step 10 is not optional.** The gate compares against
  `pipeline.processed_weeks`, and `mark_processed.py` is what writes it.
  Skipping it leaves the gate believing last week was never processed.
- **Step 1 is the only check that can catch a stale source.** Everything
  we test is downstream of the same MBIE file, so a stale-but-well-formed
  CSV passes every test in `dbo`. `aip_check.py` collects the Argus
  Singapore quote republished weekly by the Australian Institute of
  Petroleum — an independent path to the same market — and the comparison
  against `importer_cost` is `monitor_aip_gap` plus its tests. It compares
  the week-on-week *move*, never the level: the gap to our landed cost
  drifts (diesel 6.9 → 13.4 USD/bbl over Oct 2025 – Aug 2026, petrol steady
  at 7.4 – 9.6). Needs `pypdf`. Detail in `docs/mbie_notes.md`.
- **The `monitoring` schema warns and never stops the run.** Its tests
  print `WARN` and `dbt test` still exits 0 on them, so read the output —
  a green run is not the same as a quiet one. `dbt test --select monitoring`
  on its own is the fastest way to see just the signals, and
  `dbt show --select monitor_revision_summary` says what changed under us
  this week. Rationale in `docs/architecture.md`.
- **Step 6 comes before step 7, not after.** `build_period_flags.py` reads
  the panel and `backtest.py` reads the flags, so running the flags later
  leaves `backtest_results.csv` split on last week's regime values. The
  centred 9-week window means the last four weeks' numbers move every time
  a new week lands, so this is not a no-op.
- **`--full-refresh` everywhere**, per the rule at the top of this file.
  Step 8 especially: a plain `dbt seed` loads into the existing table and
  fails the moment a column is added.
- Steps 0b, 1b, 2, 3, 4, 5, 8, 9 and 10 need the capacity running. Steps 1,
  6 and 7 are local. The gate needs it too — its state lives in the
  warehouse, and there is no way to ask MBIE anything without one (see
  `pipeline/gate.py`).
- Provisional weeks are handled automatically: `backtest.py` trains only on
  Final rows and applies the model to every week, so the series extends by
  itself as MBIE finalises. Nothing to adjust by hand.
- Whole chain is about five minutes.
- `seeds/brent_daily.csv` (FRED `DCOILBRENTEU`) is diagnostic only — no
  model or forecast reads it. FRED runs a few days behind, so the newest
  week's `brent_mean` is an average of whatever days exist.

**This wants automating and moving off the laptop.** It is still eleven
steps with a hard dependency on one person's venv, one machine's Azure login
and the capacity being awake — but the two that needed a human *judgement*
rather than a human *hand* are gone: freshness is step 0b and no longer a
portal click, and "was this week already done" is step 10 rather than
memory. What remains is planned in `docs/workstreams.md`: the chain declared
once instead of remembered (W7), then GitHub Actions (W8). Until those land,
this table is the process.

## Reading the monitoring signals

`dbt test` exits 0 whether or not the `monitoring` contour warned, so the
output has to be read rather than glanced at. Nothing below stops the chain;
each line is a judgement to make before trusting the week.

| what you see | what it means | what to do |
|---|---|---|
| no `WARN` at all | the outside check agrees and no Final week moved | nothing |
| `aip_latest_week_out_of_step` → `ingest_behind` | AIP has a week we don't. Run after the ingest, this is the 19 Aug 2026 failure: `Succeeded` on a week-old file | this is the answer to a gate that said `nothing_new` — it says MBIE *has* published, so the CDN served us a stale copy. Re-run `ingest_mbie_weekly`, then step 0b again. Do not refresh Power BI |
| `aip_latest_week_out_of_step` → `aip_store_behind` | our data moved on, the store didn't: step 1 was skipped, or parsed nothing | re-run step 1 and read stderr. `no report tables parsed` means AIP restyled the PDF — the page-3 layout and the `ROW` regex in `aip_check.py` need fixing. **Our numbers are unaffected**; the check is blind until it is fixed |
| `aip_latest_week_out_of_step` → `aip_store_empty` | the store holds nothing for that fuel | `git checkout -- seeds/monitoring/aip_singapore_weekly.csv`, reload the seed. Never regenerate the file — see below |
| `aip_disagrees_on_the_newest_week` | our `importer_cost` and the Argus quote disagree on the newest week, by more than a damped move or in sign | the gate counts rows and cannot see this: a file of the right size carrying wrong numbers passes it. Read the row in `monitor_aip_gap` and only continue once satisfied |
| `revisions_rewrote_a_final_week` | MBIE changed a number on a week it had already called Final | published history has moved: `skill_26w` and `forecast_accuracy` for past weeks will no longer match what the report showed. Read the row, then record it in `architecture.md` — this has not happened yet, so the first one is worth writing down |

Revisions to weeks that are still Provisional do not warn — they happen most
weeks and are routine. `dbt show --select monitor_revision_summary --limit 20`
shows them anyway if you want to look.

### Failures that are not warnings

- **`seeds/monitoring/aip_singapore_weekly.csv` deleted.** Every dbt command
  then fails to parse — `depends on a node named 'aip_singapore_weekly' which
  was not found` — not just the monitoring ones. The whole project is stuck
  until `git checkout -- seeds/monitoring/aip_singapore_weekly.csv` brings it
  back. That file is the only copy of the weeks AIP has already deleted from
  its own site, so it is appended to and never regenerated.
- **AIP or FRED unreachable.** Step 1 prints to stderr and still exits 0:
  cached PDFs are parsed anyway, and if the FX series cannot be fetched the
  store is left untouched rather than half-converted. Either way the store
  stops advancing, which shows up next as `aip_store_behind`.
- **Capacity paused.** Everything from step 1b on fails immediately with
  `this Fabric capacity is currently not active`. Resume it and start again;
  no partial state is left behind.

## Project structure

- `pipeline/` — the weekly recompute: the gate, the closing marker, and the
  Fabric plumbing both need. See `pipeline/README.md`
- `models/silver/` — long→wide pivots (`silver_general`, `silver_fuel`)
- `models/gold/` — lag correlation + resolved + volatility
- `models/monitoring/` — revision and ingest signals, in their own warehouse
  schema; feeds nothing and stops nothing
- `seeds/periods.csv`, `seeds/variable_mapping.csv`
- `seeds/monitoring/aip_singapore_weekly.csv` — the only copy of the AIP
  weeks; append, never regenerate
- `snapshots/mbie_revisions.sql`
- `macros/pivot_variables.sql`, `macros/lag_correlation_series.sql`,
  `macros/generate_schema_name.sql` (custom schemas are used verbatim)

Full design rationale: `docs/architecture.md`
Source (MBIE) structure and gotchas: `docs/mbie_notes.md`

## dbt vars (dbt_project.yml)

- `volatility_window_weeks` — rolling window size for the volatility
  indicator (currently 6). Change here, not in SQL, then
  `dbt run --select factor_volatility`.
- `aip_move_threshold_usd` (2) and `aip_damping_ratio` (0.25) — when
  `monitor_aip_gap` raises a flag. Both are USD/bbl week-on-week
  quantities; loosen them here rather than in the model.

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
