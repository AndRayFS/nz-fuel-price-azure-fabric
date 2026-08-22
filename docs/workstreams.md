# Workstreams — plan of record, 23 Aug 2026

Twelve pieces of work, grouped by what they are about rather than by when
they happen. Each is meant to be one branch. Every entry states what
exists today, what the branch delivers, what it risks, and which files it
touches — the last so that parallel branches can be sequenced without
colliding.

This document is the plan; `docs/architecture.md` remains the record of
*why* the model is what it is, and `.claude/rules/active-items.md` remains
the list of dated obligations. Nothing here restates those.

## Dates that constrain the ordering

| date | event | consequence |
|---|---|---|
| 23 Aug 2026 | old `nz_fuel` report + semantic model retired | **done** — one publish-to-web entry, one model to refresh |
| 25–27 Aug 2026 | owner away, no laptop | nothing may be left mid-flight |
| 26 Aug 2026 | MBIE publishes (Wednesday) | **decision: skip this run**, do it 28 Aug |
| 27 Aug 2026 | Azure trial credit expires | ~NZ$245 lapses regardless |
| 28 Aug 2026 | F2 starts billing at NZ$0.729/h | every warehouse run costs real money |
| ~26 Sep 2026 | Power BI Pro trial ends | W9 must be decided before this |

Skipping the 26 Aug run costs two days of staleness on a report that
already labels itself a retrospective simulation. Rushing an unattended
pipeline into place before a trip costs more.

---

# Track 1 — Data hygiene

Four branches that fix layer boundaries. None of them is a hard
prerequisite for Track 2, but all of them are cheaper to do before CI
starts amplifying whatever is there.

## W1 — `status` through silver — **landed 22 Aug 2026**

Branch `w1-status-through-silver`. Delivered as described below, with two
departures worth stating. `accepted_values` passed on every status column,
including `importer_margin_trend_status` (open question 2, now closed), so
nothing had to be dropped for failing the test — but `Importer margin
trend` was then removed from `variable_mapping` altogether, value column
included, because nothing in the project reads it. And the models now
actually call `pivot_variables`, which until this branch was a macro no
model used. The refactor moved no numbers: `forecast_history.csv` and
`backtest_results.csv` came back byte-identical. Full record in
`architecture.md`, "Status belongs to a value, not to a week".

**Now.** `silver_fuel` pivots bronze into one row per `(Week, Date, Fuel)`
and carries values only; `Status` has no column and is dropped.
`export_panel.py` therefore reaches sideways into the snapshot
(`outer apply` on `dbo.mbie_revisions`) to recover it — a `select top 1`
with no `order by` and no `dbt_valid_to is null` filter, so on a week that
has already transitioned it may return the superseded `Provisional` row.
`backtest.py` trains on `status == 'Final'`, so that value reaches the
training filter.

**Target.** `Status` is carried the same way values are, one column per
variable, using the existing pivot shape:

```sql
max(case when Variable = 'Importer cost' then Status end) as importer_cost_status
```

No week-level aggregate is invented — the source records status per value,
and silver is a reshaping layer, not an opinion layer. `Importer margin
trend` then stops contaminating anything: its status lives in its own
column and drags nothing down. The training flag in `backtest.py` is
defined explicitly, in one visible place, over the variables the model
actually depends on.

**Steps.** Extend the pivot in `silver_fuel` (grain `Week, Date, Fuel`) and
`silver_general` (grain `Week, Date`, `Fuel = 'NA'`); drop the
`outer apply` from `export_panel.py`; define the training flag explicitly;
add `accepted_values` (`Provisional` / `Final`) on the status columns.

**No uniformity test is needed, and that is the point.** An earlier draft
of this workstream aggregated status to week level and therefore had to
enforce "status is uniform within a week". Carrying it per variable makes
that claim irrelevant — nothing depends on it any more. If a grain test on
bronze is ever wanted separately, it is `(Week, Fuel, Variable, Unit)`:
`Variable` alone collides on `Dubai crude price`, which has a USD row and
an NZD row, and that exact omission has already produced one duplication
bug in the snapshot join (`architecture.md`).

**Risks.** Widens silver by several text columns, of which only three ever
vary. Requires `--full-refresh` and therefore live capacity.
`accepted_values` may fail on `importer_margin_trend_status`: by MBIE's own
description the status field does not apply to that LOESS-smoothed column,
so whatever it carries may not be one of the two expected values. If so,
that is a finding to record — and an argument for excluding that column
from the status pivot entirely, as it is already excluded from revision
tracking.

**Depends on.** Nothing.
**Touches.** `models/silver/silver_fuel.sql`,
`models/silver/silver_general.sql`, `macros/pivot_variables.sql`,
`research/export_panel.py`, `research/backtest.py`, `models/silver/*.yml`.

## W2 — Monitoring contour — **landed 22 Aug 2026**

Branch `w2-monitoring-contour`. Delivered as described below, with three
departures worth stating. The AIP comparison became a model *and* tests
rather than one or the other: `monitor_aip_gap` keeps every week, the tests
look only at the newest, which is what makes the acknowledgement seed
unnecessary for now (open question 5, closed below). The store moved as an
ordinary dbt seed rather than a bespoke table — `git mv`, then `dbt seed`,
and the re-run of `aip_check.py` reproduced the file byte-identically, so it
was a move and not a re-derivation. And `aip_check.py` gave up blocking
entirely, including on a parse failure: it now collects and exits 0, and the
store failing to advance is itself one of the warnings.

Pointing the contour at itself produced the first finding: 29 revision
events across four snapshot runs, every one of them a still-Provisional week
being adjusted, with `Importer cost` and `Importer margin` moving in exact
opposition so the pump price never moves. No Final week has been rewritten
in the snapshot's lifetime. Full record in `architecture.md`, "The monitoring
contour — signals with no authority".

**Now.** Two quality mechanisms exist and neither is contained. Revisions
are captured by `snapshots/mbie_revisions.sql` but nothing signals that a
revision happened — historical numbers change silently, including
`skill_26w` for past weeks on a report whose whole point is showing when
the model was wrong. Separately `research/aip_check.py` fetches AIP PDFs,
parses page 3, converts via FRED, accumulates a CSV **on one laptop**, and
exits non-zero — i.e. it blocks the weekly chain from the middle of it,
on the authority of a source whose publication regime we do not know.

**Target.** One monitoring contour, holding both, producing signals and
feeding no model.

- Revision signal: a test on the snapshot reporting how many weeks changed
  in this run and in which variables. It lives where revisions live; the
  calculation path is not involved.
- AIP: storage moves off the laptop into its own warehouse schema —
  deliberately **not** bronze, so nobody mistakes it for a source. The
  comparison against `importer_cost` becomes a model or test in the same
  contour. Behaviour drops from blocking to **warning**: it highlights a
  discrepancy and the run continues. That is a deliberate reduction in
  authority, matched to how much we actually know about the source.
- Acknowledgements: a seed (`check, week, fuel, reason, acked_on`) so a
  reviewed discrepancy stops firing while new ones still do. In git, so
  every ignore carries a reason and a date. This is a sub-decision — it can
  be deferred until the first false positive makes the shape obvious.

**Risks.** AIP has no archive (11–15 reports retained; Mar–Jun 2026 is
already lost), so the local CSV is the only copy of what has been
collected — migrate it, do not re-derive it. Warning-only means a real
discrepancy can be walked past; that is the accepted trade. And moving the
store into the warehouse costs something specific: the AIP check is
currently one of only three steps that need no live capacity, and it stops
being one. Given the gate (W3) already requires the warehouse to be up
before anything runs, that is a small loss, but it is a loss.

**Depends on.** Nothing hard. Easier after W1 removes the other
snapshot reference.
**Touches.** `research/aip_check.py`, `snapshots/`, new models under a
monitoring schema, new seed, `QUICKSTART.md`.

## W3 — Freshness gate — **landed 22 Aug 2026**

Branch `w3-freshness-gate`. Delivered, but not as specified: comparison 1
turned out to be impossible, and the shape of the gate changed accordingly.

**The independent read cannot be done.** `mbie.govt.nz` sits behind Imperva,
which serves a 212-byte JavaScript challenge to every non-browser client —
Python, curl over both HTTP versions, full Chrome header sets, a primed cookie
jar, and even a curl issued after Chrome had solved the challenge from the
same egress IP. Chrome gets the file; scripts do not. Per-client, not per-IP,
so CI is no different, which answers the same question for W8 early. Full
record in `architecture.md`, "The freshness gate, and the check it could not
be". Peter Ellis independently failed to find a staleness check for this file
from R two weeks earlier, and observed it running up to ten days late — which
also weakens the original premise: two downloads of the same stale file agree
with each other and prove nothing.

**So the gate asks what arrived, not what was published.** `rowsRead` off the
copy activity via the Fabric REST API — the number the human was reading in
the portal — against bronze and against what the source held when the last
week was processed. The file grows by exactly 30 rows a week, and the 19 Aug
runs read 34,920 / 34,920 / 34,950, so the comparison is decisive on the case
that motivated the workstream.

**Three departures worth stating.** The gate no longer distinguishes "MBIE has
not published" from "the CDN served a stale copy" — both stop the chain, and
telling them apart stays with the AIP contour at warn level. It has three exit
codes rather than two (0 go, 2 nothing to do, 1 stop and look), because "exit
0 on nothing new" would let a `set -e` chain carry on. And a fourth comparison
was added that the plan did not have: nothing-new escalates to a hard stop
once the last processed week is more than fourteen days old, because a CDN
stuck on one file answers "nothing new" forever, which is the same bug wearing
a different hat.

`pipeline/` now exists, holding `gate.py`, `mark_processed.py`, `fabric_io.py`
and `test_gate.py` — the last replaying the decision over eleven cases with no
network and no capacity. W5 moves the rest of the production scripts in beside
them.

**Now.** Freshness is asked twice, four steps apart. Step 0c is a human
reading `rowsRead` on the copy activity in the portal — the only defence
against the 19 Aug failure, where two runs reported `Succeeded` while
serving a week-old file from MBIE's CDN. Step 4b is `aip_check.py` in the
middle of the chain. Neither position is principled; the second exists
only because `aip_check` reads `panel_weekly.csv`, which does not exist
until step 4.

**Target.** One gate at the entrance, three date comparisons, and no
question about freshness anywhere after it:

1. max date in the published `weekly-table.csv` vs max week in bronze —
   catches the stale CDN without portal clicking;
2. max week in bronze vs last processed week — "nothing new, exit 0";
3. if MBIE has a week bronze lacks — stop and say the ingest has not run
   or served stale.

The gate is the **only** thing in the run allowed to stop it. After it,
everything is computation.

**Unresolved: where "last processed week" lives.** Comparison 2 needs
state that survives between runs. Candidates: `max(week_date)` in
`forecast_accuracy` (no new object, but couples the gate to the report
table), or a small marker table written by the closing reconciliation (one
more object, but says exactly what it means). Decide in the branch.

**Honest caveat about "one gate".** Today the ingest is triggered by hand
before the chain runs, so all three comparisons happen at one moment. Once
W8 triggers the ingest itself, the gate necessarily splits in two: MBIE vs
last-processed *before* triggering (do not wake the capacity for nothing),
and bronze vs MBIE *after* it completes. That is still one gate with one
owner, but it is two moments, and the W8 branch should not be surprised by
it.

**Risks.** Downloading MBIE's file a second time (once by the gate, once
by the Fabric copy activity) is a small duplication, accepted in exchange
for an independent read. From 28 Aug the gate's early exit is what stops
paying for full refreshes over unchanged data.

**Depends on.** Nothing.
**Touches.** new script under `pipeline/`, `QUICKSTART.md`.

## W4 — Vintage reconstruction — **landed 23 Aug 2026**

Branch `w4-vintage-mode`. Delivered, then extended past the original scope in
the same branch: the var alone turned out to be half a tool. It moves six
objects out of eighteen and leaves `forecast_accuracy` on today's data, which
answers "how big was that revision" but not "give me the system as it was so I
can work in it" — and the second is what a vintage is for.

`pipeline/vintage.py` is the finished shape: `--as-of DATE`, `--status`,
`--return`. It restores the hand-written seeds from the commit current on that
date, runs the six-step chain, and records the state in
`pipeline.warehouse_vintage`, which the freshness gate now reads as its first
check. Code deliberately stays current — the question with no look-ahead is
what today's method would have said on the data available then. Full record in
`architecture.md`, "The revision is worth 0.003 of r, and no lag at all".

Four departures worth stating.

**`forecast_accuracy` does not mix vintage silver with a current forecast
history, as this entry claimed before the branch ran — it has no silver
dependency at all.** `dbt list --select +forecast_accuracy` returns exactly
`forecast_history` and `period_flags`, both seeds, and in a vintage run it
built *first*, before silver. So it is not wrong in a partial vintage run,
it is simply unmoved: the one gold table still showing current numbers while
everything else went back. The correction matters because the original
phrasing implied a contaminated number that a reader would go looking for.

**`dbt_project.yml` was not touched.** The plan had the var declared there,
but `simulate_cutoff_date` has always been an inline `var(..., none)` default
with no project-level entry, and matching that beat introducing a second
convention.

**Both halves of a date must mean the same instant.** The macro first
compared `dbt_valid_from <= 'DATE'` — midnight — while the git half resolved
the commit with `--before='DATE 23:59:59'`. A snapshot run on the 13th stamps
that morning, so `--as-of 2026-08-13` served the state the 12th left while the
seeds came from the 13th. Both now resolve to the end of the named day. Caught
by a row count on the first real run.

**The monitoring contour goes vintage too**, which the plan did not
anticipate: `monitor_aip_gap` descends from `silver_fuel`. In a vintage run
`aip_latest_week_out_of_step` warns, correctly — silver's newest week is
older than the AIP store's. It warns rather than fails only because W2
deliberately dropped that check from blocking to warning, so a decision made
for other reasons is what keeps a vintage run unblocked.

### What it measured on the first use

Entered at as-of 7 Aug 2026, against the current warehouse:

| | weeks | silver_fuel rows | sum(r) in lag_correlation |
|---|---|---|---|
| current | 1165 | 3495 | 243.71841837 |
| vintage @ 7 Aug | 1163 | 3489 | 236.86209402 |

**Not one `resolved_lag` changed** — all 108 rows hold the same lag in both
states, and period `05_calm_import_era` came back bit-identical, confirming
the difference is confined to the period holding the affected weeks.

A vintage differs from current in two ways at once, though — fewer weeks
*and* unrevised values — so a third run isolated the revision with
`simulate_cutoff_date` at the same date (same weeks, today's values). On
period 06 / `adjusted_retail_price`, the revision alone is worth **±0.003 to
0.004 of `resolved_r`**, in both directions, moving no lag. The two extra
weeks are worth more than the revision on `exchange_rate` (up to 0.011) and
about the same on crude.

That is the standing caveat in `architecture.md` — "absolute errors are
flattered by an unknown amount" — measured for the first time. One date, one
revision event, inside a five-week snapshot history: not a general result,
but no longer an unknown one.

### Verification

The return prong was exercised four times (vintage → current → vintage →
cutoff → current) and reproduced the pre-change fingerprint of all six tables
exactly every time, to eight decimal places. `dbt test` is PASS=83 WARN=0 on
return, and PASS=82 WARN=1 in the vintage state, the warning being the AIP
one above.

---

The entry below replaces a design this document carried until 23 Aug: an
analysis in `analyses/` plus a side file `panel_weekly_asof_DATE.csv` that
the research code could be pointed at. That was rejected for being a
half-measure. If the question is "what did we know on date N", then silver,
gold and the panel must *all* stand on date N — a vintage CSV beside a
current warehouse answers it for one file and leaves `skill_26w`, the
resolved lags and every gold table on today's data. Recording the argument
because the rejected shape looks cheaper and will suggest itself again.

**Now.** There is no way to ask "what did the data look like as known on
date N". `simulate_cutoff_date` in silver filters by *observation date*
("data up to August"), which is a different question from *vintage* ("data
as it was known in August"): the first returns today's corrected numbers for
older weeks, the second returns what was believed at the time. The snapshot
holds the versions and nothing reads them that way.

Measured 23 Aug, as-of 7 Aug against current: eight cells differ, all in
2026w31 — `importer_cost` 185.4915 → 186.1226 on diesel, crude 82 → 83
USD/bbl, with `importer_margin` moving in exact opposition. A
`simulate_cutoff_date` run to the same date returns 186.1226, a number
nobody could have known on 7 August. That gap is the whole deliverable.

**Target.** A mode, not a side file. A var `as_of_vintage` makes
`silver_fuel` and `silver_general` read `dbo.mbie_revisions` filtered by
validity —

```sql
where dbt_valid_from <= '{{ var("as_of_vintage") }}'
  and (dbt_valid_to is null or dbt_valid_to > '{{ var("as_of_vintage") }}')
```

— instead of `source('bronze', ...)`, reshaped by the same
`pivot_variables` call the models already make. Everything above follows for
free: gold reads silver through `ref()` exclusively, so `lag_correlation`,
`lag_resolved` and `factor_volatility` recompute on the vintage without a
line of change. Same objects, same schema. Return is a plain
`dbt run --full-refresh` with no var set.

This is deliberately the colour already worn by `simulate_cutoff_date`,
which has run six backtests this way — including its return path, documented
in `architecture.md`: "silver/gold are fully regenerated by a plain
`dbt run --full-refresh` with no var set afterward".

**No separate schema.** An earlier version of this design routed vintage
output to a `vintage` schema so the warehouse was never in a "wrong" state.
Dropped: Report 1's semantic model is Import and refreshed by an explicit
step, so vintage numbers cannot reach the published link without a human
running a refresh — and if one did, the report would show an earlier maximum
week, which is a visible error rather than a silent one. The separate schema
also cost work rather than saving it: `export_panel.py` holds raw SQL with
`dbo.` hardcoded and would have needed the schema parameterised.

**The chain is six steps, not one.** The var reaches gold on its own, but
`forecast_history` is a seed — computed in Python, loaded by `dbt seed` — so
a fully consistent vintage runs:

```
dbt run --full-refresh (with the var)  →  export_panel.py
   →  build_period_flags.py  →  backtest.py
   →  dbt seed --select period_flags forecast_history
   →  dbt run --full-refresh (with the var)
```

and the return runs the same six without it. Cheap in wall clock — the
whole weekly chain is about five minutes. Until that seed is rebuilt,
`forecast_accuracy` simply does not move: it descends from seeds only and
never reads silver, so in a partial vintage run it is the one gold table
still showing current numbers.

**Known limits, to be stated in the doc rather than discovered later.**
Horizon is **17 July 2026** (answered below, measured not assumed), so
anything earlier has exactly one version and a vintage run reproduces
current numbers there. Granularity is per snapshot run — five exist: 17 Jul,
31 Jul, 6, 13, 19 Aug. `Importer margin trend` is excluded from tracking by
design and cannot be reconstructed. Only MBIE data is versioned: `periods`,
`brent_daily` and the rest are seeds, so a vintage warehouse carries July
values under today's period definitions.

**Therefore the payoff today is near zero, and that is not an argument
against it.** Five vintages spanning five weeks, 29 changed cells, none of
them touching the target. A vintage `skill_26w` will differ in the third
decimal on a handful of points. What it buys is that `architecture.md`'s
standing caveat — "absolute errors are flattered by an unknown amount" —
stops being unknown. The measurement gets better every week the snapshot
runs.

**Steps.** Conditional source in the two silver models; decide the
interaction with `simulate_cutoff_date` (set together they produce a
mixture nobody can interpret — most likely refuse both at once); confirm
which gold models are meaningful in a partial vintage run; verify the return
prong reproduces current numbers byte-identically, the way W1 was verified
against `forecast_history.csv`; then QUICKSTART.

**Risks.** No longer "low, nothing is materialised" — this design overwrites
silver and gold in place and depends on the return prong actually being run.
Nothing detects a warehouse left in a vintage state: the W3 gate compares
bronze against `pipeline.processed_weeks`, and a vintage run moves neither.
The mitigation is procedural — document entry and return as one operation,
not two — and the exposure is bounded by every weekly run rebuilding
everything anyway.

Needs live capacity for each full refresh. Free until 27 Aug; billed after.

**Depends on.** Nothing.
**Touches.** `macros/weekly_prices_relation.sql` (new),
`pipeline/vintage.py` (new), `models/silver/silver_fuel.sql`,
`models/silver/silver_general.sql`, `pipeline/gate.py`, `pipeline/test_gate.py`,
`QUICKSTART.md`. Not `export_panel.py` — the warehouse moves underneath it and
the script is unchanged. Not `dbt_project.yml`, per the departure above.

---

# Track 2 — Getting off the laptop

## W5 — Split `pipeline/` from `research/`

**Now.** `research/` holds two different kinds of code under one README.
`export_panel.py`, `build_period_flags.py` and `backtest.py` run every
week on settled algorithms with no human in the loop — that is production.
`adl_*.py`, `procurement_lag.py`, `headline_results.py` and the
twenty-specification estimation loops are exploration. The README's
argument for staying offline ("estimation is a loop of twenty
specifications") is true of the second kind and was allowed to cover the
first.

**Target.** `pipeline/` for the weekly deterministic recompute, `research/`
for exploration. After the split there is no step in the weekly chain
about which one has to ask whether it is safe to run unattended.

**Risks.** Import paths and any shared helpers move; the weekly chain must
be run once end-to-end afterwards to confirm nothing was left behind. Git
history for the moved files is preserved by `git mv`, but blame across the
move is one hop harder to follow.

**Depends on.** Best done after W1 and W3, which touch the same scripts.
**Blocks.** W8 — do not migrate a directory whose production/draft
boundary is unclear.
**Touches.** `research/*` → `pipeline/*`, `research/README.md`,
`QUICKSTART.md`, `docs/report1_redesign.md` (refresh commands).

## W6 — Reproducible environment

**Now.** The venv holds 82 packages and the repository pins none of them:
no `requirements.txt`, no `pyproject.toml`, no lockfile, no devcontainer.
Only `packages.yml` (dbt packages) is version-controlled. The environment
exists in exactly one copy, on one Mac.

**Target.** Pinned dependencies and a `.devcontainer/` definition, so the
same environment can be built by CI, by Codespaces, and by anyone cloning
the repo. This is a precondition for W8 and for working from anywhere.

**Risks.** Effectively none, and it is the only item on this list that
needs neither Azure nor live capacity nor a working network path to
Fabric. Pinning may reveal that some package was only ever installed
transitively — that is a finding, not a problem.

**Depends on.** Nothing. Can be done at any time, including immediately.
**Touches.** `requirements.txt`, `.devcontainer/`, `README.md`.

## W7 — Declarative chain

**Now.** The weekly chain is eleven steps in a markdown table plus three
warnings that have to be remembered: step 5 before step 6 (the centred
nine-week window moves the last four weeks' regime values every time a new
week lands, so order is not cosmetic), `--full-refresh` everywhere, and — since
W3 — that the gate's exit code binds nobody. `rowsRead` by eye is gone; what
replaced it is a step 0b whose verdict a human still has to obey voluntarily,
because a markdown table cannot express a dependency. That is now this
branch's clearest justification: W3 made the decision correct, W7 makes it
binding.

**Target.** The chain declared once, in `Taskfile.yml`: tasks with
dependencies, order derived rather than written down, each task
addressable by name so a failed run resumes with `task <name>`. The
imperative code shrinks to what is genuinely logic — the gate comparison
(W3) and the closing reconciliation — each a small script with one job and
an exit code.

Declaring it once matters beyond tidiness: W8 then invokes the same file,
so local and CI execute literally the same chain and cannot drift apart.

**Risks.** Task's dependency model is not a data-aware DAG — it does not
know that `forecast_accuracy` is stale because a seed changed. That
remains the closing reconciliation step's job.

**Depends on.** W3 and W5 (declaring a chain whose parts are still moving
is wasted work).
**Touches.** `Taskfile.yml`, `QUICKSTART.md`.

## W8 — GitHub Actions

**Now.** Every step runs on one laptop, under one person's `az login`,
with `authentication: CLI` in `~/.dbt/profiles.yml`. A week away from the
machine is a week without an update.

**Target.** The weekly chain runs unattended on schedule. Actions is
Microsoft, so this does not leave the stack the project exists to learn;
the code stays in git and the logs stay plain text, so none of the three
objections that ruled out a Fabric notebook apply here.

**Steps.**
- Entra app registration; federated (OIDC) credentials rather than a
  stored secret.
- SPN granted the Fabric workspace role and warehouse permissions; the
  tenant setting "service principals can use Fabric APIs" enabled.
- `profiles.yml` moves into the repo using `env_var()`; dbt auth becomes
  ServicePrincipal.
- `export_panel.py` switches `AzureCliCredential` → `DefaultAzureCredential`
  so one code path serves both a local `az login` and CI.
- The ingest is triggered through the Fabric REST job API and polled,
  which finally removes the last portal step from the chain.
- Capacity resumed at the start and paused in an `always()` step.
- Scheduled by cron with the standing caveat that cron is UTC and NZ
  observes daylight saving, so the local hour drifts twice a year.

**Risks.**
- **Automation reverses a deliberate decision.** Auto-resume was turned
  off on purpose. A run costs roughly NZ$0.06 in capacity (resume, ten
  minutes, pause) — about NZ$3/year. The failure mode is a crashed run
  leaving the capacity awake, bounded by the 23:00 NZT auto-pause, so the
  exposure is hours, not unbounded. Acceptable, but it is the owner's call
  because the original decision was deliberate.
- **The gate does not split in two, as W3 warned it might.** That caveat
  assumed the gate could ask MBIE directly before triggering the ingest, so
  as not to wake the capacity for nothing. It cannot — Imperva refuses every
  non-browser client — so the gate stays one step, after the ingest, and
  waking the capacity is unconditional. Roughly NZ$0.06 a run, spent even on
  weeks with nothing new.
- **Generated artefacts — three seeds, not one.** `forecast_history.csv`
  (836 KB), `period_flags.csv` (444 KB) and the AIP store are all derived
  data reaching the warehouse by round-tripping through git. Under CI each
  weekly run becomes a bot commit and the history grows fast. The clean
  answer is for the pipeline to write them straight to the warehouse and
  retire the seed round-trip — safe *here* in a way it was not inside a
  Fabric notebook, because the code stays in git and runs reproducibly.

  This is the branch that unblocks it: a seed cannot leave git earlier,
  because `dbt seed` reads the working tree and a clean clone would fail to
  build. `panel_weekly.csv` and `backtest_results.csv` are not seeds and
  were gitignored on 23 Aug without waiting for this.

  `brent_daily.csv` joins them, corrected 23 Aug: it was first filed as
  hand-downloaded and therefore staying, but FRED serves it under a stable
  series id and its one question is already answered, so it becomes a fetcher
  in `research/` and the seed retires. That also touches `export_panel.py`,
  which joins `dbo.brent_daily`.

  `periods.csv` and `variable_mapping.csv` stay in git and are not part of
  this — they are hand-written configuration, and the reviewable history of
  why a period boundary moved is the point of them. Full reasoning in
  `architecture.md`, "Observations belong in the warehouse, configuration
  belongs in git".

  - **Do not delete `seeds/monitoring/aip_singapore_weekly.csv` until
    warehouse retention is verified.** It is the only copy of the AIP series
    in existence — the source keeps 11–15 reports and Mar–Jun 2026 is already
    lost — and git is currently its crude backup. Restore points and
    time-travel retention must be checked and configured deliberately first,
    not assumed. This subpoint exists because it is the one irreplaceable
    file in the project and a branch about Entra, OIDC and cron is exactly
    where it would be walked past.
- Public repository: secrets are not exposed to forks, and Actions minutes
  are free, but the workflow file is world-readable — no identifiers that
  are not already public.

**Depends on.** W5 and W6 hard; W7 strongly preferred.
**Touches.** `.github/workflows/`, `profiles.yml`, `pipeline/*`,
`docs/cost_notes.md`.

## W9 — Power BI workspace and licence

**Now.** Both semantic models and both reports live in **My Workspace**.
Microsoft's own documentation is unambiguous: "My Workspace isn't supported
when using service principal." So the refresh step cannot be automated
while the report lives there, and it will remain the one manual action
after W8.

A real workspace already exists — `nz-fuel-price-project`,
`bc2e3801-9a54-4154-9f46-2a9dc442cad7` — but it sits **on the F2 dedicated
capacity**, and a report served from a workspace on a paused capacity is
expected to go dark. Today's arrangement is free and survives the pause
precisely because My Workspace is not on that capacity and the model is
Import.

**Target.** A workspace that is not on F2 — Pro/shared — holding an Import
model, with the SPN added as a member. Then the refresh automates, and
publish-to-web keeps working while the capacity sleeps, because the data
is imported. Capacity is needed only for the minutes of the refresh.

**Why not DirectQuery.** It removes the refresh step but moves the load to
view time, and a public link has unpredictable viewers, so the capacity
would have to stay up: NZ$0.729/h is NZ$17.50/day, roughly NZ$525/month,
against about NZ$24/month for Pro. Import plus Pro is already the cheapest
arrangement; the only thing broken about it is where it lives. Whether
publish-to-web supports DirectQuery at all is a separate open question and
does not need answering.

**Risks.** Whether publish-to-web survives on a Free licence after the Pro
trial ends is unresolved and Microsoft's docs point both ways — that is
the pre-existing ~27 Sep item, and W9 must be settled before it. Moving a
report changes its public URL, so the link has to be reissued. Per
`CLAUDE.md`, every Power BI behaviour asserted here is to be verified in
the VM before being relied on.

**Depends on.** Independent of W8 — Actions is worth having even with the
refresh left manual.
**Touches.** Power BI service (not the repo), `.claude/rules/active-items.md`,
`docs/cost_notes.md`, `docs/architecture.md` (Stack question).

---

# Track 3 — Analysis

## W10 — The one-week model

**Now.** The next methodological piece, and the owner's stated priority
regardless of the infrastructure work. It needs no Fabric compute at all:
estimation runs offline against `research/data/panel_weekly.csv`, so it is
unaffected by the 27 Aug credit expiry and can happen at any time.

**Depends on.** Nothing. Runs in parallel with everything in Tracks 1–2.

## W11 — Apply the Report 1 redesign

**Now.** `docs/report1_redesign.md` is a spec; Power BI Desktop runs in the
VM, so applying it happens there. Two items were added on 21 Aug: small
multiples on fuel for visual 1, and episode names on the canvas rather than
in a tooltip.

**Risks.** Two Power BI mechanisms in that spec are explicitly **not
verified**: whether a line chart can carry an annotation layer at all, and
whether a visual title supports per-word colour. Both must be checked in
the VM before being treated as specified. Interacts with W9 — do not apply
a redesign to a report that is about to move.

## W12 — US retail as a second target (backlog)

**Now.** All six periods and all three factors live inside New Zealand;
there is no external benchmark. The EIA weekly US retail series
(`PET_PRI_GND_DCUS_NUS_W.xls`) is a second country asking the same
question — how many weeks does crude take to reach the pump — and the
difference between the two lags is the interesting number.

The claim that `lag_correlation` "runs on it unchanged" is too strong and
should not be planned against: the macro is period-bounded and joins to
`silver_*` relations, so US retail needs its own silver model and a
decision about whether the six period definitions — drawn around New
Zealand events — mean anything on the American side. The *method*
transfers; the wiring does not come free.

Distinct from the roadmap's existing EIA item in `architecture.md`, which
is about *Brent as a daily crude benchmark* and was revised downward on
13 Aug in favour of a Singapore refined-product quote. This is retail, not
crude, and a target, not a factor.

**Risks.** Adds a second source with its own revision behaviour, holidays
and definitions; the comparison is only honest if both sides are on the
same basis. Genuinely optional — it buys narrative, not correctness.

---

# Dependency graph

```
W1 status ──┐
W3 gate ────┼─→ W5 split ─→ W7 chain ─→ W8 Actions
W6 env ─────┘                              │
                                           └─→ (W9 completes unattended operation)
W2 monitoring   ─ independent
W4 vintage      ─ independent
W10 model       ─ independent
W11 report      ─ interacts with W9
W12 benchmark   ─ backlog
```

Only three hard dependencies exist: W5 and W6 before W8, and W3/W5 before
W7. Everything else is preference, and preference should not be presented
as sequencing.

**The three tracks are a grouping, not an order.** Reading them top to
bottom suggests infrastructure comes before analysis, which is wrong on the
facts: W10 is the stated priority, needs no capacity, no CI and no cleanup,
and is unaffected by the 27 Aug credit expiry. It can start immediately and
run alongside everything else. W6 is likewise free-standing and needs
nothing but a text editor.

**Twelve entries is not twelve equal branches.** W10-W12 are analysis rather
than engineering and do not need the same branch discipline, and W12 is
explicitly backlog. Realistically this is about seven branches of structural
work. W4 was in this sentence as "small" until 23 Aug; the redesign from a
side file to a whole-chain mode makes it an ordinary branch.

# Conflict map for parallel branches

| file | wanted by |
|---|---|
| `research/export_panel.py` | W1, W5 |
| `research/backtest.py` | W1, W5 |
| `models/silver/silver_fuel.sql` | W1 |
| `models/silver/silver_general.sql` | W1 |
| `models/silver/_silver__models.yml` | W1 |
| `QUICKSTART.md` | W2, W3, W5, W7 |
| `research/aip_check.py` | W2, W5 |
| `.claude/rules/active-items.md` | W9 |

`QUICKSTART.md` is wanted by four branches; leave its rewrite to whichever
lands last rather than editing it in each. `export_panel.py` was wanted by
three until W4 was redesigned on 23 Aug to move the warehouse under the
script rather than change it.

# Open questions

1. ~~`min(dbt_valid_from)` on the snapshot — the vintage horizon.~~
   **Answered 23 Aug 2026: 17 July 2026**, which is the one-off backfill date
   rather than the first `dbt snapshot` run — the backfill worked as intended,
   31,347 of 31,484 rows start there, so an as-of query returns a full panel
   and not just the rows that changed. Five vintages exist (17 Jul, 31 Jul,
   6, 13, 19 Aug), 29 rows are closed, and the snapshot spans 2004w17-2026w33
   at every one of them. Consequence for W4: before 17 July there is exactly
   one version, so a vintage run reproduces current numbers there. (W4)
2. ~~Does `accepted_values` hold for `importer_margin_trend_status`, or does
   that column have to be dropped from the pivot?~~ **Answered 22 Aug 2026:**
   it holds — bronze carries `Final`/`Provisional` on that variable exactly
   as on every other, with no NULLs. The column is gone regardless: the
   whole variable was removed from `variable_mapping`, because nothing
   reads it. (W1)
3. Does publish-to-web work from a Pro workspace on a Free licence after
   the trial? (W9, and the pre-existing ~27 Sep item)
4. Can a Power BI line chart carry annotations without positioned text
   boxes? (W11)
5. ~~Should the AIP acknowledgement seed exist from the start, or wait for
   the first false positive to show what fields it needs?~~ **Answered
   22 Aug 2026:** neither — it is not needed yet. Scoping the tests to the
   newest snapshot run and the newest shared week means a flag is raised
   once rather than every week after, so nothing accumulates to be silenced.
   The seed becomes necessary the first time a discrepancy *persists* across
   weeks, and that is when its fields will be obvious. (W2)
6. ~~Where does "last processed week" live — `forecast_accuracy` or a marker
   table written by the reconciliation step?~~ **Answered 22 Aug 2026:** a
   marker table, `pipeline.processed_weeks`, in its own warehouse schema.
   `forecast_accuracy.week_date` agrees with it exactly today, but it exists to
   serve a report and could be rebuilt, filtered or repointed without anyone
   thinking about the gate. The cost is that the gate always needs live
   capacity — accepted, and it was unavoidable anyway once the independent MBIE
   read proved impossible. (W3)
