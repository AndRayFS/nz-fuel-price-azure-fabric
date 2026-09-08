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

**Building the venv from scratch** (new machine, or the existing one is
suspect): `python3.12 -m venv .venv` then
`.venv/bin/pip install -r requirements.txt`. That file pins every package to
the version this project's results were produced under; `requirements.in`
records which of them are direct dependencies and why. Do not upgrade as a
side effect of something else — bump the pin, re-run `pipeline/backtest.py`,
and confirm the seeds come back byte-identical first.

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
| **Weekly data refresh (IMPORTANT)** | Always use `--full-refresh` — plain `dbt run` has been observed to not reliably pick up new bronze rows for the models downstream of bronze. `dbt run --full-refresh`, which is what `task build` does |
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
| **The weekly chain** | `task weekly` — see below. `task --list` for the individual steps |

## Weekly data update — the full chain, in order

MBIE publishes on Wednesdays. This is the whole sequence; skipping a step
leaves Report 1 showing last week's numbers with this week's date.

```bash
# 0. resume the capacity and run `ingest_mbie_weekly` — still a portal step
task weekly
```

That is the whole chain. It runs the nine steps below in order, and stops at
the gate unless the gate says go — the ordering and the dependency live in
`Taskfile.yml` now, not in whoever is pasting.

| task | step | what it is |
|---|---|---|
| `gate` | 0b | **the gate.** Nothing after it runs unless it exits 0 |
| `aip` | 1 | collect the AIP weeks, straight into `monitoring.aip_singapore_weekly` |
| `snapshot` | 2 | revision history |
| `build` | 3 | bronze -> silver / gold / monitoring |
| `test` | 4 | everything outside `monitoring` must pass; monitoring warns |
| `panel` | 5 | panel out to `data/panel_weekly.csv` |
| `flags` | 6 | regime axes, from the panel, into `dbo.period_flags` |
| `backtest` | 7 | refit + forecasts, into `dbo.forecast_history` |
| `report` | 8 | rebuild the table Report 1 reads |
| `close` | 9 | record the week as processed |

**A failed run resumes by name** — `task report`, not the whole chain again.
`task --list` prints this table from the file itself; `task offline` runs just
steps 6 and 7, which need no capacity; `task env` checks the venv before
anything else does.

Every step is still one command you could type by hand, and `--full-refresh`
is written into the file rather than remembered.

Then refresh the Power BI dataset.

Notes:

- **Step 0b is the only step allowed to stop the run, and its exit code is
  the whole point.** `0` carry on, `2` nothing to do (stop, quietly), `1` stop
  and go and look. It reads `rowsRead` off the copy activity through the
  Fabric REST API — the number a human used to read in the portal — and
  compares it against bronze and against what the source held when the last
  week was processed. On 19 Aug 2026 the ingest reported `Succeeded` twice
  while serving a week-old file out of MBIE's CDN: green pipeline, 60 green
  tests, report a week stale. The gate returns `2` on that run, so the chain
  never starts. Reasoning in `pipeline/gate.py`; full account of the failure
  in `docs/architecture.md`.
- **The verdict binds, since W7.** Every task in `weekly` comes after `gate`,
  so a non-zero exit stops the run. `task` prints its own failure line on a
  `2` as well, which is why the gate task explains in words first that
  stopping was the point. Running a step directly (`task build`) deliberately
  skips the gate — that is for resuming a run, not for starting one.
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
- **`--full-refresh` everywhere**, per the rule at the top of this file. The
  step that needed it hardest is gone: since 7 Sep 2026 the derived tables are
  written to the database by the scripts that compute them, so nothing
  round-trips through git and no seed is reloaded weekly.
- **Every step now needs the capacity up.** `flags` and `backtest` still
  compute offline, but they write their results to the database rather than to
  a CSV, so the old split into "local steps" is gone. The gate needs it too —
  its state lives there, and there is no way to ask MBIE anything without one
  (see `pipeline/gate.py`).
- Provisional weeks are handled automatically: `backtest.py` trains only on
  Final rows and applies the model to every week, so the series extends by
  itself as MBIE finalises. Nothing to adjust by hand.
- Whole chain is about five minutes.
- **Brent is not part of this chain** (since 7 Sep 2026). Nothing in the
  weekly recompute reads it, so it is fetched on demand instead:
  `python research/fetch_brent.py` writes `data/brent_daily.csv` from FRED
  (`DCOILBRENTEU`, no key). FRED runs a few days behind, so the newest week is
  an average of whatever days exist.

**What is left to automate is the machine, not the sequence.** The eleven
steps are one command since W7, and the two that needed a human *judgement*
rather than a human *hand* went earlier: freshness is the gate rather than a
portal click, and "was this week already done" is step 10 rather than memory.
What remains is a hard dependency on one person's venv, one machine's Azure
login, the capacity being awake, and two manual bookends — resuming the
capacity with the ingest at the front, and the Power BI refresh at the back.
That is W8 in `docs/workstreams.md`, which invokes this same `Taskfile.yml`
so CI and this laptop cannot drift apart.

## Reading the monitoring signals

`dbt test` exits 0 whether or not the `monitoring` contour warned, so the
output has to be read rather than glanced at. Nothing below stops the chain;
each line is a judgement to make before trusting the week.

| what you see | what it means | what to do |
|---|---|---|
| no `WARN` at all | the outside check agrees and no Final week moved | nothing |
| `aip_latest_week_out_of_step` → `ingest_behind` | AIP has a week we don't. Run after the ingest, this is the 19 Aug 2026 failure: `Succeeded` on a week-old file | this is the answer to a gate that said `nothing_new` — it says MBIE *has* published, so the CDN served us a stale copy. Re-run `ingest_mbie_weekly`, then step 0b again. Do not refresh Power BI |
| `aip_latest_week_out_of_step` → `aip_store_behind` | our data moved on, the store didn't: step 1 was skipped, or parsed nothing | re-run step 1 and read stderr. `no report tables parsed` means AIP restyled the PDF — the page-3 layout and the `ROW` regex in `aip_check.py` need fixing. **Our numbers are unaffected**; the check is blind until it is fixed |
| `aip_latest_week_out_of_step` → `aip_store_empty` | the store holds nothing for that fuel | the store is a warehouse table now, so there is no file to restore: re-run step 1 and read stderr. If the table itself was lost, `monitoring.aip_singapore_weekly` is the one thing in this project with no upstream — see below |
| `aip_disagrees_on_the_newest_week` | our `importer_cost` and the Argus quote disagree on the newest week, by more than a damped move or in sign | the gate counts rows and cannot see this: a file of the right size carrying wrong numbers passes it. Read the row in `monitor_aip_gap` and only continue once satisfied |
| `revisions_rewrote_a_final_week` | MBIE changed a number on a week it had already called Final | published history has moved: `skill_26w` and `forecast_accuracy` for past weeks will no longer match what the report showed. Read the row, then record it in `architecture.md` — this has not happened yet, so the first one is worth writing down |

Revisions to weeks that are still Provisional do not warn — they happen most
weeks and are routine. `dbt show --select monitor_revision_summary --limit 20`
shows them anyway if you want to look.

### Failures that are not warnings

- **`monitoring.aip_singapore_weekly` lost or truncated.** It stopped being a
  seed on 7 Sep 2026 and is now a warehouse table that `pipeline/aip_check.py`
  appends to and never truncates. It holds the only copy of the weeks AIP has
  already deleted from its own site — Mar–Jun 2026 is gone upstream — so
  nothing can rebuild it. If it is lost, the recovery is warehouse time travel
  (30-day retention), not a re-fetch and not `git checkout`. `dbt` will also
  stop parsing if the source disappears, since `monitor_aip_gap` reads it
  through `source()`.
- **AIP or FRED unreachable.** Step 1 prints to stderr and still exits 0:
  cached PDFs are parsed anyway, and if the FX series cannot be fetched the
  store is left untouched rather than half-converted. Either way the store
  stops advancing, which shows up next as `aip_store_behind`.
- **Capacity paused.** Everything from step 1b on fails immediately with
  `this Fabric capacity is currently not active`. Resume it and start again;
  no partial state is left behind.

## Project structure

- `pipeline/` — the weekly recompute, end to end: the gate, the panel
  export, the regime flags, the backtest, the closing marker, and the Fabric
  plumbing they share. See `pipeline/README.md`
- `research/` — estimation and exploration, plus `aip_check.py`, the one
  weekly step that stayed here because a restyled PDF needs a person. See
  `research/README.md`
- `data/` — derived, gitignored, rebuilt by steps 5–7: `panel_weekly.csv`
  and `backtest_results.csv`. Owned by neither package; nothing in git
- `models/silver/` — long→wide pivots (`silver_general`, `silver_fuel`)
- `models/gold/` — lag correlation + resolved + volatility
- `models/monitoring/` — revision and ingest signals, in their own warehouse
  schema; feeds nothing and stops nothing
- `seeds/periods.csv`, `seeds/variable_mapping.csv`
- `monitoring.aip_singapore_weekly` — a warehouse table since 7 Sep 2026, not
  a seed; the only copy of the AIP weeks. `pipeline/aip_check.py` appends and
  never truncates
- `snapshots/mbie_revisions.sql`
- `macros/pivot_variables.sql`,
  `macros/generate_schema_name.sql` (custom schemas are used verbatim)

Full design rationale: `docs/architecture.md`
Methods and measurements: `docs/research.md`
Source (MBIE) structure and gotchas: `docs/mbie_notes.md`

## dbt vars (dbt_project.yml)

- `aip_move_threshold_usd` (2) and `aip_damping_ratio` (0.25) — when
  `monitor_aip_gap` raises a flag. Both are USD/bbl week-on-week
  quantities; loosen them here rather than in the model.

## Putting the system on a past date

```bash
python pipeline/vintage.py --as-of 2026-08-13   # go there
python pipeline/vintage.py --status             # what is loaded right now
python pipeline/vintage.py --return             # come home
```

Use the script, not the var by hand. `as_of_vintage` alone moves six objects
out of eighteen and leaves `forecast_accuracy` — the table Report 1 leads
with — on today's data, with nothing saying so. The script runs the whole
six-step chain, restores the hand-written seeds from the commit that was
current on that date, and records what the warehouse holds in
`pipeline.warehouse_vintage`. The freshness gate reads that marker and
refuses to run the weekly chain on a vintage warehouse.

**Two different questions, two vars.** Setting both raises a compilation
error rather than returning a mixture:

- `simulate_cutoff_date` — **observation date.** Which weeks are visible.
  Values are today's, corrections included.
- `as_of_vintage` — **vintage.** What was believed on that date. Silver
  reads the snapshot instead of bronze.

**Horizon is 17 July 2026**, the snapshot backfill date; earlier dates are
refused because every row has one version there. Five data vintages exist
(17 Jul, 31 Jul, 6, 13, 19 Aug), and a date resolves to the state as that
day *ended*, so `--as-of 2026-08-13` includes the 13 Aug snapshot run.

**Code stays today's, deliberately.** The question worth asking is what
today's method would have said on the data available then — that is the one
with no look-ahead in it. Old code is reachable through git if archaeology is
ever wanted, but it could not read a vintage without backporting
`weekly_prices_relation`, so it would not be purely historical either.

Three things to expect:

- **A run takes a few minutes** and needs live capacity: two full refreshes
  with three Python steps between them.
- **`aip_latest_week_out_of_step` warns** in a vintage, correctly — silver's
  newest week is older than the AIP store's. WARN, not ERROR.
- **The script refuses to start** if `seeds/` or `data/` have
  uncommitted changes while the warehouse holds current data, because it
  rewrites both and restores them from git afterwards. Once a vintage is
  loaded a dirty tree is expected and it proceeds.

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
