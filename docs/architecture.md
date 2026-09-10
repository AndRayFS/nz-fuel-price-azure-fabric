# Architecture decisions — the loading contour

This documents the *why* behind the design choices in the contour that runs
every week without a human in the loop: MBIE's file arriving, bronze through
silver, the gate that decides whether the chain may run at all, the monitoring
that is allowed to notice but never to stop, and the semantic model behind the
published report. Written for future-me as much as for anyone else reading the
code.

**The measurements live in `docs/research.md`**, split out on 3 Sep 2026. The
line between the two files is *consumption*, not language and not directory:
what runs weekly and feeds the published report is here, what a person runs
when a person chooses the specification is there. Python sits on both sides of
that line — `export_panel.py`, `build_period_flags.py` and `backtest.py` are
production and are documented here.

**Every number here is an illustration measured on a stated date, not a current
value.** The source revises, weeks finalise in blocks, and parts of the chain
can be run by hand — so a figure written down here says what was measured, not
what holds today. Recompute before quoting one, and only when the answer turns
on the digit rather than on the shape.

## Medallion layers — what each one is actually for

- **Bronze** stores the raw MBIE snapshot exactly as it arrives. Nothing is
  cleaned, nothing is renamed. Truncate + reload every run, because the
  source itself only ever offers a full-history file, not incremental
  deltas — there's nothing to merge.
- **Silver** is where all schema complexity is absorbed. This is the one
  layer that's allowed to know the source used to look different.
- **Gold** shouldn't need to know the source ever changed. It answers
  questions (lag correlations), not "what does the raw data look like."

The goal isn't eliminating change — sources evolve, always. The goal is
localizing it, so a source-side change means editing one silver model, not
chasing it through the whole project.

## Seed-driven pivot, not hardcoded CASE WHEN

`seeds/variable_mapping.csv` maps `variable_name` (+ optional `unit_filter`,
since "Dubai crude price" appears twice with different units) to a
`canonical_name`. The silver models generate their pivot from this seed at
compile time (`dbt_utils.get_query_results_as_dict`), not from a hand-written
list of `CASE WHEN` blocks.

Adding a new tracked variable is a one-line CSV addition, not a SQL edit —
this is the whole point of the seed-driven approach argued for in Part 2 of
the writeup, actually implemented rather than just proposed.

**Adapter note:** the official dbt-fabric adapter's `run_query()` fails
inside model compilation on this project (`'None' has no attribute 'table'`).
`dbt_utils.get_query_results_as_dict` — which also calls `run_query()``
internally — works fine. This is not fully understood, just empirically
confirmed; if `run_query()` breaks again on a future dbt/adapter upgrade,
try the dbt_utils wrapper before assuming the whole approach is broken.

## TRY_CAST instead of CAST, backed by tests instead of by trusting the source

Source values are parsed with `TRY_CAST(Value AS FLOAT)`, not `CAST`. A
single malformed value in 20+ years of history shouldn't fail the entire
weekly pipeline run.

The tradeoff: `TRY_CAST` fails silently, turning bad data into `NULL` instead
of raising an error. That's closed by explicit `not_null` tests on every
value column that feeds the gold layer (`dubai_crude_usd`, `dubai_crude_nzd`,
`exchange_rate`, `board_price`, `adjusted_retail_price`). If a source ever
ships something non-numeric, the *test* fails loudly — not the pipeline, and
not a silently blank chart three weeks later.

## Snapshot: what's tracked, what isn't, and why

`snapshots/mbie_revisions.sql` tracks Provisional → Final revisions via
`check` strategy on `Value` and `Status`, joined against
`variable_mapping` and filtered to `track_revisions = 'true'`.

`Importer margin trend` is excluded. It's LOESS-smoothed, which means adding
one new week's data point re-fits the *entire* historical curve — a diff
between two weekly snapshots showed ~7,000 changed rows, ~99% of them this
one column, spanning back to 2004. That's smoothing noise, not a real
revision, and including it would bury genuine revisions under thousands of
cosmetic ones every week. **Superseded 22 Aug 2026: the series was dropped
from `silver_fuel` entirely**, so there is no longer anything for the
snapshot to exclude — see "`Importer margin trend` dropped from silver
entirely" below. Bronze still holds the rows.

**Join gotcha hit here:** the snapshot's join to `variable_mapping` originally
matched on `variable_name` alone. Since "Dubai crude price" has two rows in
the seed (USD and NZD units), every crude-price bronze row matched *both*
seed rows and got duplicated in the snapshot. Fixed by also joining on
`unit_filter`. Worth remembering for any future variable that shares a name
across units.

**One-off backfill:** a manually-saved copy of the 17 July bronze file was
merged into the snapshot after its first run, so the snapshot's history
starts from 17 July rather than from whenever `dbt snapshot` first happened
to run. Changed rows got an explicit historical version; unchanged rows had
their `dbt_valid_from` pulled back to 17 July rather than left at the
snapshot's first-run date — otherwise an as-of-17-July query would return
only the handful of rows that changed, not a full point-in-time snapshot.
This was a one-time manual fix, not a repeatable pattern — there's no
general backfill mechanism here.

## Why dbt at all, given it's a single source right now

Could have used Data Factory Script Activity directly against the Warehouse.
Chosen dbt instead because the project is explicitly meant to grow past one
source: version-controlled transformations, lineage that's generated (not
hand-maintained and therefore never stale), tests that fail before a
dashboard quietly goes wrong, and `ref()`-based environment independence.
None of that pays for itself on day one with a single source — it pays off
the day a second one shows up.

## DAX filter-context bugs — same underlying cause, three symptoms

Three measures broke the same way while building the forecast, worth
recording as one lesson rather than three unrelated fixes:

1. `Volatility Trend`'s comparison window was hardcoded to 21 days instead
   of reading `volatility_config[window_days] / 2` — see the lag layer at
   the end of this file.
2. `Forecast Pct Change`/`Forecast Confidence` were reading
   `SELECTEDVALUE(lag_resolved[factor/target/fuel])` — but the Factor/
   Target/Fuel slicers are built on `lag_correlation`'s columns, not
   `lag_resolved`'s (the two tables aren't directly related to each other).
   `SELECTEDVALUE` against an unfiltered column just returns `BLANK()`,
   which silently propagated into "no forecast" for every selection.
3. After fixing (2), the forecast still changed when switching the
   *Period* slicer, even though the intent was "always show the live,
   open period's forecast regardless of what's selected." The `periods`
   table has an active relationship to `lag_resolved` (1-to-many on
   `period_id`); an explicit `CALCULATE(..., lag_resolved[period_id] =
   CurrentPeriodId)` filter does *not* override a filter arriving through
   that relationship from a different table — the two compete for the same
   column, and DAX resolves that as "no rows," not "explicit filter wins."
   Fixed by adding `ALL(lag_resolved)` as the first argument to strip every
   ambient filter (including relationship-propagated ones) before applying
   the intended explicit filters.

The general pattern worth remembering: an explicit `CALCULATE` filter on a
column doesn't automatically beat a filter that arrived at that same
column via an active relationship from a filtered table elsewhere on the
page. When a measure is meant to deliberately ignore what's selected
elsewhere on the report, `ALL()` the target table first, then apply the
intended filters — don't assume the explicit filter alone wins.

Also needed: determining "the current open period" via
`ISBLANK(periods[end_date])` reliably returned blank, for reasons not
fully diagnosed (a stray blank row that Power BI auto-adds to the "one"
side of a one-to-many relationship — visible as an extra 7th row when
`COUNTROWS(ALL(periods))` was checked against the known 6 — was the
leading suspect, but not conclusively confirmed). Replaced with
`start_date = MAX(start_date)` instead, which sidesteps the issue and is
arguably clearer intent anyway ("the most recently started period") than
relying on a null end date.

## Refreshing the published report — the service could never do it until 13 Aug 2026

> **The live public link, and the report and model ids, are recorded three
> subsections down**, under "The old `nz_fuel` retired" — a heading about a
> deletion, which is where they landed rather than where anyone would look
> for them. Note added 3 Sep 2026.

Report 1 lives in **My Workspace** as an **import** model (confirmed via
`INFO.VIEW.TABLES()`: every table reports `StorageMode = Import`), so its
data is a snapshot held inside the model. It does not follow the warehouse
— a bronze reload plus `dbt run` leaves the report showing last week's
numbers until the model itself is refreshed.

Until 13 Aug 2026 the service had **never** refreshed it: refresh history
was empty and scheduled refresh was disabled. The data got there by
publishing from Power BI Desktop, which loads rows locally and uploads them
together with the model — the service never needs a connection to the
source for that, which is exactly why the missing connection went unnoticed
for so long.

**`Refresh now` failed with `Premium_ASWL_Error`:**

```
this semantic model uses a default data connection without explicit
connection credentials. Please replace the default data connection ...
with an explicit cloud or gateway data connection.
```

The model reached the warehouse through a *default* connection. Two things
make this awkward to diagnose:

- The **Data source credentials** section in the model's Settings is greyed
  out, which reads as a permissions problem. It isn't — the binding lives
  in **Gateway and cloud connections**, a different section on the same
  page. Ownership was never the issue (`configuredBy` matched the
  signed-in account, `isOnPremGatewayRequired: false`).
- `GET /datasets/{id}/datasources` returns no `datasourceId` and no
  `gatewayId` when the connection is default. That is the fastest way to
  tell the two states apart — a properly bound model returns both.

**Fix:** create a ShareableCloud connection (type `SQL`, auth `OAuth2`,
privacy `Organizational`) against the warehouse endpoint, then map it to
the model under Gateway and cloud connections. After that `Refresh now`
completed in about five seconds and the model picked up the new week.

### Two models named `nz_fuel` — the trap that cost the most time

There were **two** semantic models and two reports carrying the same name:
one pair in My Workspace, one pair in the `nz-fuel-price-project`
workspace. Both reports were published to web — the old Fabric-workspace
embed code described as "dead and should be deleted" earlier in this
document had in fact never been deleted, so two public links existed,
backed by two different models.

What that cost on 13 Aug: the cloud connection was bound to the wrong
model, and a successful refresh updated a report nobody was looking at
while the public link stayed a week stale. The names are identical in the
UI; the only reliable discriminator is the URL — **`groups/me` means My
Workspace**, anything else is the project workspace. `GET /myorg/reports`
versus `GET /myorg/groups/{id}/reports` separates them unambiguously and is
worth preferring over clicking.

**Cleaned up 13 Aug 2026:** the report and the semantic model in the
`nz-fuel-price-project` workspace were both deleted, leaving exactly one
publish-to-web artifact (verified via
`/admin/widelySharedArtifacts/publishedToWeb`, which now returns a single
entry). A pbix backup of the deleted report was exported first, to
`~/nz-fuel-price-project/nz_fuel_projectws_backup_20260813.pbix` — outside
the repo.

### `nz_fuel_v2` inherited the same unbound-connection fault — 19 Aug 2026

The 13 Aug fix bound a ShareableCloud connection to the **`nz_fuel`** model.
`nz_fuel_v2`, published from Desktop on 17 Aug, is a separate model and got
a *default* connection of its own, so its first service refresh (19 Aug)
failed with the same `Premium_ASWL_Error`. The diagnostic from 13 Aug still
holds and is one call: `GET /datasets/{id}/datasources` returns
`datasourceId` + `gatewayId` for `nz_fuel` and neither for `nz_fuel_v2`.

**Fixed the same day** by pointing `nz_fuel_v2` at the connection `nz_fuel`
already uses — the two models read the same warehouse, so no second
connection was needed. The refresh then completed in 5.5 s, and a DAX probe
(`POST /datasets/{id}/executeQueries`) confirmed the import actually landed:
`forecast_accuracy` 6,363 rows, max `week_date` 2026-08-14, matching the
warehouse row-for-row. That probe is worth keeping as the verification step
— `Completed` on a refresh says the model reloaded, not that it reloaded
*the new week*.

**Any model published from Desktop starts unbound**; expect this on every
new model, not just this one.

### The old `nz_fuel` retired — 23 Aug 2026

The six-day parallel run ended as planned: the original `nz_fuel` report and
its semantic model were deleted from My Workspace, leaving `nz_fuel_v2` as
the only report, the only import model and the only publish-to-web link
(`/admin/widelySharedArtifacts/publishedToWeb` back to a single entry, as
after the 13 Aug cleanup). A pbix backup went to
`~/nz-fuel-price-project/nz_fuel_backup_20260823.pbix`, outside the repo.

The whole thing ran through the Power BI REST API from the terminal, with a
token from `az account get-access-token --resource
https://analysis.windows.net/powerbi/api` — the same user identity the
portal uses, no separate app registration. `GET/DELETE /myorg/reports/{id}`,
`/myorg/datasets/{id}` and `GET /myorg/reports/{id}/Export` (which returns
the pbix bytes directly, 200, no async polling) all work that way, and the
admin `widelySharedArtifacts` endpoint too. Worth preferring over clicking
for anything where picking the wrong `nz_fuel` is the failure mode.

**The ShareableCloud connection survives its original model.** The 13 Aug
connection was created against `nz_fuel` and later re-used by `nz_fuel_v2`;
deleting the `nz_fuel` dataset did not take it down —
`GET /datasets/{v2}/datasources` still returns both `datasourceId` and
`gatewayId` afterwards. Connections are workspace-level objects, not model
children. Checked rather than assumed, because a broken binding here would
only have surfaced at the next weekly refresh.

From now on each weekly update refreshes **one** model, not two. The live
report — the only public link this project has — is

`app.powerbi.com/view?r=eyJrIjoiZGQ4YzE2OWUtNTg1Zi00NzY4LWFiYTUtNGJmYTJlZmNkOWFiIiwidCI6IjY2YWVkMTI5LWFjZWQtNDgyOS05NzAxLTZiNzMxNTY3NWEwNCJ9`

(report `c31bf57c-86a4-40cb-908e-ea49ae773a2e`, model
`221ea91d-5855-4c0c-a5da-4c4af0a2650a`). It was recorded only in
`.claude/rules/active-items.md` until now, which is a file written to go
stale; it belongs here.

### Weekly sequence from here

> **Stale as a chain, 3 Sep 2026 — `QUICKSTART.md` is canonical.** The six
> steps below predate the freshness gate (W3) and `mark_processed.py`, so
> following them would run the chain without ever asking whether there is
> anything new to run, and without closing the run afterwards. What this
> subsection is still for is the *reason* below: which steps need the
> capacity up and which do not.

`resume capacity → run ingest_mbie_weekly → dbt snapshot → dbt run
--full-refresh → dbt test → refresh the semantic model`.

The model refresh reads the warehouse, so it needs the capacity **up**.
Viewing the report afterwards does not, since import mode serves from the
model — which is the whole point of the My Workspace arrangement described
above. Scheduled refresh is now technically possible, but it would have to
fire inside the window when the capacity happens to be running (it
auto-pauses at 23:00 NZT and is resumed by hand), so it is left disabled
rather than half-working.

## The ingest read a week-old file and reported success — 19 Aug 2026

MBIE published week `2026w33` (14 Aug) at 01:01 UTC on 19 Aug. Two
consecutive `ingest_mbie_weekly` runs that morning finished `Succeeded`
with `rowsRead = rowsCopied = 34920` — exactly the previous week's file,
34,950 rows minus the 30 rows of the new week. Nothing failed: bronze was
truncated and reloaded with stale content, `dbt run --full-refresh` and all
60 tests passed on it, and `silver_fuel` stayed at 2026-08-07.

**The activity's own row count is the only signal.** A copy activity that
fetches an old file is indistinguishable from a correct run at every layer
below it — the pipeline is green, the tests are green, and the report is a
week behind. Compare `rowsRead` against the source, not the run status.

**Cause: CDN edge caching, not the pipeline.** `mbie.govt.nz` sits behind
Imperva (`x-cdn: Imperva`). The same URL served different bytes to
different callers that morning:

| request | etag | rows |
|---|---|---|
| plain URL, from Auckland | `"c85b0d15"` | 34,950 |
| plain URL, from Fabric (Australia East) | — | 34,920 |
| URL + any query string | `"6a850076-2be92b"` | 34,950 |

The two etag *formats* are the tell: `c85b0d15` is Imperva's own, the
`inode-size` form is the origin's. A query string misses the edge cache key
and reaches origin. The AU PoP was still holding a copy cached before
01:01 UTC; `cache-control` on the response is only `no-transform`, so the
edge is free to decide its own TTL and nothing in the response says when it
expires.

**Fix, applied to the pipeline definition:** the HTTP source's
`HttpServerLocation` now carries a per-run cache-buster, appended to the
connection's base URL —

```json
"relativeUrl": { "value": "@concat('?cb=', ticks(utcnow()))",
                 "type": "Expression" }
```

— after which the next run read 34,950. The URL itself stays in the
connection (`Weekly-fuel-price-monitoring-MBIE andrei`); only the pipeline
changed. Cost: one origin fetch a week, which is what the ingest was always
meant to be doing.

Both the pipeline definition and the connection were read and written
through the Fabric REST API (`getDefinition` / `updateDefinition`), not the
portal.

**The designer flags that expression, and is formally right — 27 Aug 2026.**
Validating the pipeline reports `'concat' does not have an overload that
supports the arguments given: (StringLiteral, Int)`: `ticks()` returns an
integer and Data Factory's `concat` is typed over strings. It is a
design-time complaint only — the expression evaluates at runtime, and the
34,950-row read above is the proof, since without a query string that run
would have returned 34,920. The typed form is

```json
"relativeUrl": { "value": "@concat('?cb=', string(ticks(utcnow())))",
                 "type": "Expression" }
```

**Applied 27 Aug 2026**, after that day's chain had finished, through
`getDefinition` / `updateDefinition` — one part changed, `updateDefinition`
returned 200 synchronously, and reading the definition back confirms the typed
form is in place. It was deliberately not done mid-run: changing the ingest
definition while the result of a run is being checked adds a variable exactly
where one is least wanted.

The urgency was low either way — if the cache-buster ever stopped being
appended, the edge would serve a stale file, and that is what the gate returns
`nothing_new` on. **Still unverified at runtime:** the next `ingest_mbie_weekly`
run is the first that will evaluate the new form, and the number to read off it
is `rowsRead` — 35,010 on a normal week, or 34,980 if the query string stopped
reaching origin.

## A copy that has landed is not a copy that can be read — 10 Sep 2026

Bronze is a Lakehouse: the copy activity writes Delta files into OneLake. No
T-SQL reaches those files directly. Everything that reads bronze — the gate,
and `snapshots/mbie_revisions.sql`, which are the only two — goes through the
**SQL analytics endpoint**, a separate catalogue that is synchronised from the
Delta layer asynchronously. The two can disagree, T-SQL cannot tell you which
version it is serving, and nothing documents how long the gap lasts.

**Measured with a disposable probe**, a copy pipeline identical to the
production one (same HTTP source, same `LakehouseTableSink`, same
`OverwriteSchema`) writing to `probe.sync_probe` with an extra column carrying
`@utcnow()`, so two otherwise identical runs could be told apart:

| | |
|---|---|
| new table written | invisible to `INFORMATION_SCHEMA` at 19 s, 1.5 min, 3.7 min, **8 min** |
| `refreshMetadata` | Succeeded in **7 s**, table visible immediately after |
| existing table overwritten | endpoint still served the **previous** version 8 s later |
| `refreshMetadata` | Succeeded in **6 s**, new version visible immediately after |

Eight minutes is where the measurement stopped, not a ceiling.

**This is why the weekly run of 10 Sep 2026 failed**, and why the run of
3 Sep 2026 failed before it. The gate reported `ingest_did_not_land` — the
copy read 35,040 rows while bronze held 35,010 — and it was reporting
correctly on what it had been given. The load itself was fine: the Delta
commit is timestamped 22:52:25 UTC and the parquet beside it matches the
activity's `dataWritten` to the byte.

**Why it worked for months before that.** Nothing changed in the loader —
sink configuration is identical across every run back to 13 Aug, and
`rowsRead` equals `rowsCopied` in all of them. What changed is who asks and
how soon. The ingest used to be a person clicking Run in the portal and then
going to say so; whatever they did next took minutes, and the endpoint caught
up inside that gap. CI asks 26 seconds later. The gate did not start failing
because something broke — it started failing because the pause a human had
been supplying for free was removed, and the gate is the only thing that ever
checked.

**The fix belongs to the ingest, not beside it.** `run_ingest.py` now calls
`fabric_io.refresh_sql_endpoint()` as its last act, because the ingest's
contract is that bronze holds the file *and can be read*, and until that call
only the first half is true. `POST
/v1/workspaces/{ws}/sqlEndpoints/{id}/refreshMetadata?preview=true`,
asynchronous, polled to `Succeeded` — note that the `Location` it returns
points at a regional host rather than `api.fabric.microsoft.com`, so it needs
its own poller. Both readers of bronze sit behind it. `task sync-endpoint`
exposes the same call for the path where the copy is deliberately skipped.

Waiting instead of forcing would also work and was rejected: it bills capacity
for an interval nobody documents — roughly 30 minutes a week, some NZ$19 a
year — to avoid a call that takes six seconds.

## The freshness gate, and the check it could not be — 22 Aug 2026

W3 specified an independent read: download `weekly-table.csv` here, compare
its newest week against bronze, and catch a stale CDN without anyone clicking
through the portal. The independence was the point — every layer we own is
downstream of one file, so the only honest check comes from outside.

**It cannot be done from a script.** `mbie.govt.nz` sits behind Imperva, and
Imperva serves a 212-byte JavaScript challenge to anything that does not look
like a browser:

| client | result |
|---|---|
| Chrome | 2,877,739 bytes, 34,950 rows, etag `"6a850076-2be92b"` |
| Python `urllib` | 212 bytes, `_Incapsula_Resource` challenge |
| curl, http/2 and http/1.1 | 212 bytes |
| curl with a full Chrome header set | 212 bytes |
| curl with a primed cookie jar | 212 bytes |
| curl *after* Chrome solved the challenge from the same IP | 212 bytes |

The last two rows are the finding. Both clients egress from the same address
— `118.148.160.56`, checked on both sides — so this is not IP reputation and
not the sandbox: it is a per-client decision, made below the HTTP layer. A CI
runner would fare no better, which settles the same question for W8. The
Fabric copy activity is unaffected and still fetches the file.

Peter Ellis hit the same wall from R three weeks earlier and wrote it into
his code as a shrug: *"Not sure how to determine if it is 'stale' or not,
seems to get 10 days out of date at least"*
(`freerangestats.info/blog/2026/08/08/petrol-prices`). His observation is
worth more than the workaround he didn't find — it says the published file
itself can be well behind, which weakens the original plan on its own terms:
two downloads of the same stale file agree with each other and prove nothing.

**What the gate does instead.** It asks what arrived rather than what was
published. `rowsRead` off the copy activity, through the Fabric REST API, is
the number a human was reading in the portal, and it is decisive: the file
grows by exactly 30 rows a week.

| run | rowsRead |
|---|---|
| 06 Aug | 34,890 |
| 13 Aug | 34,920 |
| 19 Aug 04:26 | 34,920 ← a week-old file, `Succeeded` |
| 19 Aug 04:30 | 34,920 ← and again |
| 19 Aug 04:36 | 34,950 ← after the cache-buster fix |

Three comparisons: the run happened, recently, and completed; what it read
equals what bronze holds; and the source has grown since the week we last
processed. The third is the stale-CDN detector, and it deliberately does not
try to distinguish "MBIE has not published yet" from "the CDN served last
week's file" — both mean *do not run the chain*, and telling them apart is
what the AIP contour is for, at warn level.

**Three API behaviours found by trying them.** Activity detail hangs off
`/v1/workspaces/{ws}/datapipelines/pipelineruns/{runId}/queryactivityruns`,
with the pipeline id absent from the path; the three routes the item and job
APIs suggest all return 404. `lastUpdatedAfter`/`lastUpdatedBefore` are
effectively mandatory: omit them and the call returns HTTP 200 with an empty
activity list, which reads exactly like a run that copied nothing.

And the endpoint is **flaky** — roughly one failure in ten identical calls,
measured with the capacity *active*, in two shapes: HTTP 500 `UnknownError`,
and a refused connection. An earlier reading of the same 500 blamed a paused
capacity; that was wrong, and only running it repeatedly with the capacity up
showed it. Neither shape says anything about the run being asked about, so
both are retried four times with a short backoff, honouring `Retry-After`;
4xx other than 429 is our own fault and is not retried. The gate additionally
fails **closed**: anything that stops it reaching a verdict becomes
`gate_check_failed` and exit 1, one line rather than a traceback, so a
transient outage never reads as a fault in the data — and never opens the
gate. `getDefinition`, by contrast, genuinely does need the capacity active,
returning `CapacityNotActive`.

**The escalation that stops "nothing to do" becoming the same bug.** A CDN
stuck on one file looks identical every week, and a gate that answers
"nothing new" forever is the 19 August failure in slow motion. So the same
comparison becomes a hard stop once the last processed week is more than
fourteen days old — two missed publications.

**State lives in `pipeline.processed_weeks`**, its own warehouse schema
alongside `monitoring`, written by `pipeline/mark_processed.py` as the last
step of the chain. `forecast_accuracy.week_date` was the alternative and
today the two agree exactly, but it couples the decision "may the chain run"
to a report table that exists for another reason. The cost of the choice is
stated rather than hidden: the gate now always needs live capacity, so the
W8 idea of asking MBIE before waking it does not survive — and could not
have, since there is no way to ask MBIE.

The decision is a pure function and `pipeline/test_gate.py` replays it
against eleven cases, the 19 August runs among them, with no network and no
capacity.

## Status belongs to a value, not to a week — 22 Aug 2026

`silver_fuel` and `silver_general` pivoted bronze into one row per week and
carried values only; `Status` was dropped on the way through. To get it
back, `export_panel.py` reached sideways into the snapshot with an
`outer apply (select top 1 r.Status ... where r.Date = f.Date)` — no
`order by`, no `dbt_valid_to is null`. On a week that had already
transitioned, that could return the superseded `Provisional` row, and
`backtest.py` trained on `status == 'Final'`, so the wrong value would have
reached the training filter rather than any output.

Status is now carried the way values are: one column per variable
(`importer_cost_status`, `adjusted_retail_price_status`, …), produced by
the same pivot. `macros/pivot_variables.sql` — written earlier and never
actually called — is now what both models use, once for `Value` with the
`TRY_CAST`, once for `Status` without it, so the `case when` shape lives in
one place instead of four.

**No week-level status is computed anywhere, and that is the point.** MBIE
records status per value. An earlier draft of this work aggregated it to
the week and therefore had to defend "status is uniform within a week"; per
variable, nothing depends on that claim. The training filter states its own
dependencies instead — six variables in `backtest.py`
(`TRAIN_STATUS_COLS`) and the same six in `headline_results.py`, being the
series `net`, `d_cost` and `dev` are built from. `dubai_crude_nzd` is not
among them: the only method that ever read it was `report1_ish`, withdrawn
7 Sep 2026 (`research.md`, "The reconstructed published formula loses to
doing nothing").

**What bronze actually contains** (checked 22 Aug 2026, all 24
variable/unit pairs): `Final` from 2004-04-23 to 2026-03-27 and
`Provisional` from 2026-04-03 to 2026-08-14, with no NULLs and no third
value anywhere. So status *is* uniform within a week today — the change is
that no model now depends on its staying that way. `accepted_values`
(`Provisional`/`Final`) on all eleven status columns passes; the open
question about `Importer margin trend` is answered below.

**The refactor moved no numbers, which is how it was checked.** The
re-exported panel matched the previous one in every value cell across 3,495
rows; the new six-column flag agreed with the old single-column one on
every row (3,435 final, 60 provisional — 20 weeks × 3 fuels); and
`seeds/forecast_history.csv` and `data/backtest_results.csv` came
back byte-identical to the committed versions.

### `Importer margin trend` dropped from silver entirely

It was already excluded from revision tracking as LOESS noise (see
`docs/mbie_notes.md`). The status work made the question sharper: whether
to give a smoothed presentation series a status column at all. The answer
was to stop loading the series. Nothing reads it — not the gold models, not
the analyses, not the panel, not the `nz_fuel_v2` semantic model (which
holds only `forecast_accuracy`), and not the old `nz_fuel` report, whose
definition references `silver_fuel` only for `Date`. Every number this
project publishes is computed here rather than taken from MBIE's smoothing.

Removal is one line in `seeds/variable_mapping.csv`: the pivot is
seed-driven, so both the value column and its status column disappear with
it. Bronze is untouched and still holds the rows, so restoring the series
is the same one line in reverse.

## The monitoring contour — signals with no authority — 22 Aug 2026

Two quality mechanisms existed and neither was contained. Revisions were
captured by `snapshots/mbie_revisions.sql` and then read by nobody, so
historical numbers could change without anything saying so. `aip_check.py`
did the opposite: it sat in the middle of the weekly chain and exited
non-zero, halting a recompute of New Zealand numbers on the authority of an
Australian PDF whose publication regime we do not know.

Both now live in one place, `monitoring` — a warehouse schema of its own,
three models and a seed, produced by the same `dbt run` as everything else
and read by nothing. Every test in it is `severity: warn`. That is the whole
design: **the contour is allowed to notice, never to stop.** Authority is
kept proportional to how much the check actually knows, and the run's single
stopping point is left for the freshness gate (W3).

It is deliberately not in bronze. The AIP store is not a source — nothing
downstream of silver reads it — and putting it in bronze would eventually
invite someone to treat it as one.

`macros/generate_schema_name.sql` overrides dbt's default so a custom schema
is used verbatim instead of being prefixed onto `target.schema`; the object
is `monitoring.monitor_aip_gap`, not `dbo_monitoring.monitor_aip_gap`. Every
model with no `schema` config is unaffected and verified still to resolve to
`dbo` — silver, gold and the snapshot all did after the change, and the full
`dbt build` came back 99 nodes, PASS=99.

### What the revision history actually contains

> **Two of the rules below expired on 26–27 Aug 2026** — the release that
> finalised the June quarter did all three of the things this section says
> had never happened. The paragraph recording that sits at the end of the
> section rather than here; read it before treating any count below as
> current. The *shape* survives. Note added 3 Sep 2026.

The first thing the contour was pointed at itself. Over four snapshot runs
(31 Jul, 6, 13 and 19 Aug 2026) the snapshot holds **29 revision events, all
of one kind**: a Provisional week revised while still Provisional. Not one
Provisional → Final transition, and not one Final week rewritten.

The pattern is tight enough to state as a rule and then watch for exceptions:

- Each run revised **exactly one week** — the second-most-recent — and never
  reached further back.
- Only three variables have ever moved: `Importer cost`, `Importer margin`
  and `Dubai crude price`. `Board price`, `Adjusted retail price`,
  `Price excluding tax`, `Taxes`, `GST` and `ETS` are tracked and have never
  changed.
- `Importer cost` and `Importer margin` move in **exact opposition**: summed
  per (run, week, fuel) the two deltas net to zero in all twelve groups. The
  pump price is not being restated; the split of it between landed cost and
  margin is.
- Crude revisions are whole-dollar (132 → 133 USD/bbl, 87 → 88 NZD/bbl),
  which is the rounding already documented in `docs/mbie_notes.md` showing up
  as movement.

**So revisions have so far touched the model's inputs and never its target.**
That is worth knowing before reading too much into it: the snapshot's history
starts 17 July 2026 and MBIE's last finalisation was 27 March, so the run has
never yet been present for the event the report is most exposed to — a Final
week changing under a published `skill_26w`. `revisions_rewrote_a_final_week`
exists for exactly that moment and has, correctly, never fired.

**Both of those statements expired on 26–27 Aug 2026.** The run of that week
carried, in one release, all three of the things this section says had never
happened:

- **39 Provisional → Final transitions** (thirteen weeks × three fuels), the
  June quarter finalising as a block.
- **A revision to the target.** `adjusted_retail_price` moved by 1.861 c/L on
  diesel and 0.848 on petrol across those weeks — the recalculated quarterly
  factor. The claim that the target had never been revised in 1,164 weeks was
  true when written and is not now.
- **`revisions_rewrote_a_final_week` fired for the first time**, on a 40-week
  rewrite of 2023–24 at 0.00002–0.00022 c/L. That is what
  `revision_noise_threshold_cpl` in `dbt_project.yml` was set for, the same
  day.

What survives is the *shape*: `Importer cost` and `Importer margin` still
move in exact opposition, and the pump price was restated only by the
quarterly factor, uniformly across a quarter — not week by week. See
`docs/mbie_notes.md`, "What a finalisation actually does".

### Porting the AIP check to SQL, and checking the port

The comparison moved out of `aip_check.py` and into
`models/monitoring/monitor_aip_gap.sql`, which reads `importer_cost` and
`exchange_rate` from silver directly. That removes the reason the check sat
at step 4b: it depended on `panel_weekly.csv`, which does not exist until
step 4. Collection is now step 1 and needs no warehouse; the comparison
happens where the data already is.

Per the lesson from the R port, the SQL was checked against the reference it
replaced rather than against itself. The pandas calculation and the model
agree to three decimals on the newest week (diesel level 172.160, markup
11.998; petrol 124.712, markup 8.833), and the markup ranges reproduce the
figures the docs already carried: diesel 6.911–13.414, petrol 7.406–9.559.

Both flag branches were then made to fire, because a check nobody has seen
trigger is not a check. Loosening `aip_damping_ratio` to 0.99 through
`--vars` flagged 17 of 33 rows `stale_suspected` and made
`aip_disagrees_on_the_newest_week` report `WARN 2` while `dbt test` still
exited 0 — the blocking-to-warning change, demonstrated rather than asserted.
Setting the ratio to 0 instead put the one sign-opposed week in the data
(2025-11-21, diesel: ours −0.042 against Argus +0.098) through the second
branch as `sign_disagreement`. `aip_latest_week_out_of_step` was exercised in
both directions by filtering one side back a week: it returns `ingest_behind`
— the 19 August failure, seen from outside — and `aip_store_behind`, which is
new and covers the case the old script could not have, its own collection
silently stopping.

That last case is why `aip_check.py` no longer exits non-zero even when the
PDF layout defeats the parser. A restyled Australian report is not a reason
to stop recomputing New Zealand numbers; it stops the store advancing, and
the store failing to advance is itself a warning.

### No acknowledgement seed, and the reason it is not needed yet

The plan allowed for a seed of acknowledged discrepancies so that a reviewed
one stops firing. It is not built, because the tests are scoped to the newest
snapshot run and the newest shared week rather than to all of history: last
week's flag is not re-raised this week, so nothing accumulates that would
need silencing. The models keep the full history for anyone who wants to
look. The case that would force the decision is a discrepancy that persists
across weeks — AIP dropping a fuel, say — and that is the point at which the
seed's fields become obvious rather than guessed.

### What this costs

The AIP check was one of only three steps that needed no live capacity, and
its comparison half now does. Collection still runs anywhere. Given that the
gate (W3) will require the warehouse to be up before anything else runs, the
loss is small — but it is a loss, and it was taken knowingly.

### Two holes found by breaking it on purpose — 22 Aug 2026

The contour was tested by removing the AIP store, not only by reading it, and
that turned up two things the design had asserted rather than checked.

**`severity: warn` does not cover database errors.** With an empty seed file
dbt-fabric has nothing to infer types from and made `fuel` an `int`; the
`accepted_values` test then failed to cast `'Regular Petrol'` and raised a
*Database Error*, which is an ERROR regardless of severity, and took three
downstream nodes down as SKIP. Warn severity governs a test that returns rows,
not a test that cannot run. Fixed by pinning `column_types` on the seed, so an
empty file still produces the right shape — verified by loading a
headers-only file and getting a clean build.

**An empty store was silent.** Every AIP check grouped the store by fuel, so
with nothing in it there was nothing to compare and all of them passed by
having no rows to look at — the loudest possible failure producing the
quietest possible output. `aip_latest_week_out_of_step` now lists the two
expected fuels itself and `left join`s the store to them, which turns an empty
store into `aip_store_empty` rather than into silence. The general lesson is
worth keeping: a check that derives its own expectations from the data it is
checking cannot see that data disappear.

Deleting the seed file outright is worse than emptying it and cannot be made
into a warning: `ref('aip_singapore_weekly')` stops resolving and *every* dbt
command fails to parse, monitoring or not. It is in git, restoring it is one
`git checkout`, and `QUICKSTART.md` says so under "Failures that are not
warnings".

Network failure was hardened the same way, for the same reason: the docstring
claimed the script always exits 0, which was untrue the moment AIP or FRED was
unreachable. Both are now caught — the AIP media API failing leaves the cached
PDFs to be parsed, and a FRED failure leaves the store untouched rather than
half-converted. Simulated both; both exit 0 and the seed came back
byte-identical.

### The FX half, and two ways it was wrong — 10 Sep 2026

The first CI run of the chain past the gate produced no AIP data at all. The
step went green, as designed, on `could not fetch the FX series (The read
operation timed out); store left unchanged` — the graceful degradation above,
working exactly as written, and degrading the project's only outside opinion
on the ingest to nothing. Worth stating plainly: exiting 0 is right, but a
component that has produced nothing for two consecutive runs is not a footnote.

**The source was in the wrong place.** `aip_check.py` fetched DEXUSAL from
`fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSAL`, which answers this
laptop in about a second and timed out twice at 60 s from a GitHub runner.
Measured from a runner rather than guessed at (probe workflow, run
34434535269):

| | |
|---|---|
| `fredgraph.csv` via curl | HTTP 200 in 2.9 s |
| `fredgraph.csv` via urllib | read timeout at 60 s |
| `api.stlouisfed.org`, no key | HTTP 400 in 0.18 s |
| `api.stlouisfed.org`, keyed | HTTP 200 in 0.2 s |
| Yahoo, the fallback candidate | HTTP 429 |

So nothing is blocked and FRED is reachable from CI in full: what fails is
that one host under that one client. Why is unresolved and deliberately not
chased — the answer would not change what to do. Note the last row: Yahoo,
which we would have moved to had FRED been unreachable, is the one that
actually refuses GitHub egress. The measurement was worth its minute; the
guess it replaced would have been wrong.

The fetch now goes through the FRED API with a key, held as the repository
secret `FRED_API_KEY` and required rather than optional. There is no fallback
to the graph host, because a silent fallback to the thing known to fail in CI
is the failure shape this change exists to remove.

**And the window was chosen by counting rows.** The conversion took
`fx.loc[:w].tail(5).mean()` — the last five observations up to the stamped
Friday. When the series reaches that Friday, those five are Mon–Fri of that
week. When it does not, the same expression silently returns an older window
and says nothing. FRED's lag is not a constant: DEXUSAL ended at 28 Aug on
8 Sep 2026 and at 4 Sep on 10 Sep.

Two consecutive report weeks sharing a frozen rate would zero out the FX part
of the week-on-week move, which is the only thing `monitor_aip_gap` compares —
so the failure would land precisely on the quantity the check exists to
measure. And it would be permanent, not transient: `warehouse_write.append_new`
inserts weeks the store does not hold and never revisits one, so a rate
computed from the wrong days is written into the history and stays.

The window is therefore stated as dates, `[w-4, w]`, and a week the series
does not reach is dropped with a message naming it. Nothing is lost by
waiting — every AIP report carries two weeks, and the store accumulates, so
the next run collects the week once FRED has caught up.

One detail that looks like a nicety and is not: coverage is read from the
frame *before* `dropna`. FRED publishes US holidays as rows valued `"."`, so
"how far does the series reach" and "what can be averaged" are different
questions, and reading the first off the dropped frame would reject any week
whose Friday happened to be a holiday.

Four stored weeks change value under the new window — 14 Nov 2025, 2 Jan,
23 Jan, 20 Feb 2026, each a four-trading-day week where the old expression
reached into the previous week for a fifth. Up to 0.36%. `append_new` will
not rewrite them, and they were left alone.

Verified where it had to be, which was not this laptop: the key exists only
as a repository secret, so the real `add_usd` was exercised against the real
API from a runner over synthetic weeks, one of them deliberately beyond any
coverage. Six priced with six distinct rates, the uncovered one refused by
name — and the six matched, to five decimals, what the old CSV route computes
here. Two endpoints, two machines, the same numbers.

## Observations belong in the warehouse, configuration belongs in git — 23 Aug 2026

Eight CSVs are version-controlled and four of them are rewritten every week.
Today that costs little: `.git` is 12 MB. Under CI (W8) each weekly run
becomes a bot commit, and ~2.9 MB of churn per week starts accumulating in
the history forever. The W8 risk list already named `forecast_history.csv`
as the case to fix; the rule below generalises it, because the same argument
covers three more files.

**The rule is not "no data in git".** The boundary is not size and not file
type — it is *who produced it*:

- **Observations accumulate on their own** — a source publishes them, or a
  script derives them. They belong in the warehouse, which is the tool built
  for that. `forecast_history`, `period_flags`, `panel_weekly`,
  `backtest_results`, and the AIP store — and since 7 Sep 2026 all of them
  actually are: the first two and the AIP store are written straight to the
  database by the scripts that compute them (`pipeline/warehouse_write.py`),
  the other two are local files outside git. Brent belonged in this list until
  7 Sep 2026; it turned out to belong in neither place, since nothing reads it
  — it is fetched when a question needs it and kept nowhere.
- **Configuration and hypotheses are written by a person.** They belong in
  git, and their value is mostly the history: who moved a boundary, when, and
  what the commit message said. `periods.csv` is six hand-drawn period
  boundaries that this project calls a hypothesis in half a dozen places;
  `variable_mapping.csv` is eleven rows of mapping. Neither accumulates.
  Moving them into the warehouse would trade reviewable history for nothing —
  no warehouse backup reconstructs *why* a period boundary moved.

So the file count barely changes. What changes is that no derived table
round-trips through version control on its way into the warehouse.

**What today's arrangement actually gets wrong.** Not duplication — `dbo.periods`
and `dbo.variable_mapping` exist *because* `dbt seed` put them there, so the
CSV is the single truth and the table is its copy. The real defect is the
footgun underneath: editing one of those tables directly appears to work and
is silently discarded by the next `dbt seed`. Making the warehouse the master
for observations removes that class of surprise for everything that is not
hand-written config.

**Sequencing, and why it is not one job.** Removing a *seed* from git breaks a
clean clone: `dbt seed` reads the working tree, finds nothing, and the build
fails. So `forecast_history`, `period_flags` and the AIP store cannot leave
until something regenerates or hosts them on a fresh checkout, and that is
exactly what W8 builds. They are recorded there.

`panel_weekly.csv` and `backtest_results.csv` are not seeds — no `ref()` and
no build step reads either — so they were gitignored immediately rather than
waiting for a branch that depends on W5 and W6.

**`brent_daily.csv` was misfiled here on 23 Aug and is corrected the same day.**
The first version of this note kept it in git on the grounds that "download it
yourself" does not work, the procedure being written down nowhere. That is an
argument for writing the procedure down, not for storing the data: FRED serves
it under a stable series id (`DCOILBRENTEU`), so a script fetches it in a few
lines. It is not the AIP case, where no archive exists at all — nothing about
it is irreplaceable, only unrecorded.

Its purpose is also spent. It was acquired to settle one question — whether
MBIE's weekly crude number is Friday's quote or the Mon–Fri mean — and the
answer is measured and recorded above. What remained was two diagnostic
columns in the panel that no model, no forecast and no script read.

**Done 7 Sep 2026, and not as the fetcher-in-`pipeline/` this paragraph
previously called for.** Putting it in `pipeline/` would have made it a weekly
step, and the weekly chain is the wrong place for something nothing in that
chain depends on: a step no one needs can only ever fail. So Brent left the
regular procedure altogether. `research/fetch_brent.py` pulls the series on
demand into `data/`, `export_panel.py` no longer joins it, and the seed is out
of git — verified by rebuilding both derived seeds from a panel without the
two columns and getting byte-identical files. The fetcher reproduces the
retired seed exactly (5,650 shared dates, maximum difference 0.0000) and
reaches further back, since FRED holds daily Brent from 1987 and the seed
began at MBIE's own start date.

`dbo.brent_daily` was dropped by hand on 7 Sep 2026, along with two tables
that had spent an hour in the wrong schema. If Brent ever earns a place in the
weekly recompute — a second factor, a crack spread, a check on MBIE's crude
column — the script moves to `pipeline/` and this paragraph is what has to
change first.

**One file is irreplaceable, and the rule must not be applied to it carelessly.**
`seeds/monitoring/aip_singapore_weekly.csv` is the only copy of the AIP series
that exists anywhere: the source retains 11–15 reports and Mar–Jun 2026 is
already lost. Git is currently serving as its crude backup. Moving the master
into the warehouse is right, but only once warehouse retention has been checked
and configured deliberately — restore points and time-travel retention, verified,
not assumed. The CSV does not get deleted before that.

**The public-repository argument this retires.** `export_panel.py` promised that
the committed panel made every number in `docs/` reproducible without an Azure
subscription. That promise was always weak — rebuilding the panel needs the MBIE
ingest and a warehouse, so the CSV let a reader check arithmetic but never the
pipeline. A public repository publishes the code; it is not a data store.

## The revision is worth 0.003 of r, and no lag at all — 23 Aug 2026

`simulate_cutoff_date` has always answered "weeks up to date N", with today's
corrected values inside them. It could not answer "what was believed on date
N". The snapshot held the versions and nothing read them that way, so the
standing caveat under the walk-forward results — "the panel is the current
vintage, so absolute errors are flattered by an unknown amount" — stayed
unknown by construction.

A var, `as_of_vintage`, now swaps silver's source from bronze to
`dbo.mbie_revisions` filtered by validity. Bronze cannot serve this: it holds
one copy of the current MBIE file and every ingest overwrites it. The snapshot
*is* the version record, which fixes the horizon at 17 July 2026 — the
backfill date, not the first `dbt snapshot` run — with five vintages available
(17 Jul, 31 Jul, 6, 13, 19 Aug).

Nothing downstream changed. Gold reads silver exclusively through `ref()`, so
`lag_correlation`, `lag_resolved` and `factor_volatility` recompute on the
vintage with no edit. Same objects, same schema, no parallel warehouse: the
return is a plain `dbt run --full-refresh` with no var, which is the shape
`simulate_cutoff_date` has used since the backtests.

### Three states, and what separates them

A vintage differs from the current warehouse in two ways at once — it has
fewer weeks *and* it has unrevised values. Reading the difference as "the
revision effect" would conflate them. So three runs, at as-of 7 August 2026,
period `06_iranus_2026`, target `adjusted_retail_price`:

| factor / fuel | current | cutoff @ 7 Aug | vintage @ 7 Aug |
|---|---|---|---|
| crude NZD / Diesel | 0.89938868 | 0.90003096 | 0.89659953 |
| crude NZD / Regular | 0.92265504 | 0.92261073 | 0.92603805 |
| crude USD / Diesel | 0.90406797 | 0.90487102 | 0.90167715 |
| crude USD / Regular | 0.92813865 | 0.92858547 | 0.93225722 |
| exchange rate / Diesel | 0.36780094 | 0.37288308 | 0.36841345 |
| exchange rate / Regular | 0.49021143 | 0.50135591 | 0.50031742 |

The middle column holds the same weeks as the right one and today's values,
so **vintage minus cutoff is the revision alone**: ±0.003 to 0.004 of
`resolved_r`, in both directions. Current minus cutoff is the two extra weeks:
larger than the revision on `exchange_rate` (0.011 on Regular), comparable on
crude.

**Not one `resolved_lag` moved.** All 108 rows carry the same lag in the
vintage as in the current warehouse, and `05_calm_import_era` came back
bit-identical, which is the expected confinement — only the period holding the
affected weeks can change.

So the flattering is real, measured, and small where it has been measured: the
lag machinery is unaffected and the correlation moves in the third decimal.
One date, one revision event, five weeks of snapshot history — this is a
measurement, not a general result, and it gets better every week the snapshot
runs.

### Two things the branch found rather than planned

`forecast_accuracy` does not participate. `dbt list --select +forecast_accuracy`
returns `forecast_history` and `period_flags` and nothing else — both seeds —
and in a vintage run it builds first, before silver exists. It is therefore not
a contaminated number in a partial vintage run, it is an unmoved one: the only
gold table still showing current values while the rest went back. A fully
consistent vintage needs `export_panel.py` → `build_period_flags.py` →
`backtest.py` → `dbt seed --select period_flags forecast_history` → a second
`dbt run`, and the same five on the way home. `period_flags` belongs in that
list because it is derived from the panel by rule and `backtest.py` reads it
alongside the panel — omitting it would leave the regime axes standing on
today's data while the prices went back.

The monitoring contour goes vintage as well, because `monitor_aip_gap`
descends from `silver_fuel`. `aip_latest_week_out_of_step` warns during a
vintage run — correctly, silver's newest week is older than the AIP store's —
and warns rather than fails only because W2 dropped that check from blocking
to warning for unrelated reasons. A decision made about source authority is
what keeps vintage runs unblocked.

### Which objects actually move, checked one by one

`binary_checksum(*)` summed per table, every object in the warehouse, current
against vintage @ 7 Aug. Six move and twelve do not, and the twelve are not one
category but four.

**Moves (6).** `silver_fuel`, `silver_general`, `lag_correlation`,
`lag_resolved`, `factor_volatility`, `monitoring.monitor_aip_gap`. Note that
`lag_correlation` and `lag_resolved` keep their row counts (900 and 108) and
change values only, so a row count is not a sufficient check for whether a
vintage is loaded.

**Seeds — the var cannot reach them (5).** `periods`, `variable_mapping`,
`period_flags`, `forecast_history`, `monitoring.aip_singapore_weekly`. The
first two are hand-written and *should* stay fixed. The last three are derived
and are exactly what the six-step chain rebuilds. (`brent_daily` was a sixth
until 7 Sep 2026, when Brent left the weekly chain.)

**The version history and its monitors (3).** `mbie_revisions`,
`monitor_revisions`, `monitor_revision_summary`. These read the snapshot
directly, and the snapshot is the *source* of the vintage rather than a
consumer of it — it holds every version at once and no as-of filter applies.
Correctly unchanged: the revision contour keeps reporting on all of history
while silver stands on one date.

**Pipeline state (1).** `pipeline.processed_weeks` is untouched, which is the
mechanical reason nothing detects a vintage warehouse — the freshness gate
compares bronze against this table and a vintage run moves neither.

**And one that descends from silver yet did not move.** `volatility_config`
was rebuilt and came back bit-identical, because it computes its baseline over
`period_type = 'calm'` only — periods 02 and 05. Every week the 7 Aug vintage
changes lives in `06_iranus_2026`, which is not calm, so its input window was
untouched. This is contingent, not structural: a revision landing on a calm
week would move it. Do not read the invariance as a property of the model.

`forecast_accuracy` is the twelfth, covered above: seeds only, no silver
ancestor at all.

### From six objects to the whole system

The var on its own was half a tool, and the half it delivered was the half
that is easy to misread: silver and the lags standing on a date while
`forecast_accuracy` — the table Report 1 leads with — stands on today, with
nothing anywhere recording the discrepancy. Useful for measuring a revision;
useless for the thing a vintage is actually for, which is picking up the whole
system as it was and working in it — re-cutting a report, testing a hypothesis
without look-ahead.

`pipeline/vintage.py` is the whole operation. `--as-of DATE`, `--status`,
`--return`.

**Two versioned stores, and each holds what the other cannot.** The snapshot
holds MBIE's numbers, which are not in git. Git holds `periods` and
`variable_mapping`, which are hand-written and not in the snapshot. A vintage restores from both: the seeds come from
`git rev-list -1 --before='DATE 23:59:59'`, the data from the validity filter.
The line in `workstreams.md` that called this a limit — "full historical
fidelity is a git question, not a snapshot one" — turned out to name the
mechanism rather than a shortcoming.

**Both halves now resolve to the END of the named day**, which the first
implementation got wrong in a way worth recording. The macro compared
`dbt_valid_from <= 'DATE'`, i.e. against midnight, while the git half used
`--before='DATE 23:59:59'`. A snapshot run on the 13th stamps that morning's
hour, so `--as-of 2026-08-13` returned the state the *12th* left, with 1163
weeks, while the seeds came from the 13th. Caught by the row count on the
first real run, not by reading the code.

**Code stays current, and that is the design.** "What would today's method
have said on the data available then" is the question without look-ahead in
it; "what did the report say that day" is archaeology and would reproduce
bugs this project has since found and documented. Old code is reachable
through git, but it could not read a vintage without backporting
`weekly_prices_relation` — so it would not be purely historical either, and
the choice is between two impure options rather than between pure and impure.

**A seed that did not exist yet is kept, not deleted.** The case that
prompted this was `brent_daily.csv`, which arrived on 15 Aug 2026, so a
vintage of the 13th had no version to restore, and deleting it would have
broken the panel export. Brent left the chain on 7 Sep and both remaining
seeds predate every reachable vintage, so the handling is currently inert —
kept because the next seed to arrive will hit it again. An approximation that
says which way it leans beats both a failure and a silent substitution.

**The marker earns its place by making the state answerable.**
`pipeline.warehouse_vintage` is append-only, newest row wins, and the gate
reads it as its *first* check — before anything about freshness, because a
vintage warehouse would pass every other check while being unfit to run. The
concrete hazard: a weekly chain over a vintage would `dbt seed` the vintage
`forecast_history` sitting on disk and rebuild `forecast_accuracy` from it on
top of current silver, publishing a report mixing two dates from a run in
which nothing failed.

### Verified end to end

Round trip on 23 Aug 2026, to 13 August and back. Going out, every object
moved that should: `forecast_accuracy` 6363 → 6354 rows, `forecast_history`
likewise, `period_flags` 3495 → 3492, and `variable_mapping` 11 → 12 rows —
the 13 August config still carried `Importer margin trend`, which W1 removed
that same morning, so the historical configuration genuinely applied rather
than being nominally restored.

Coming back, all thirteen `binary_checksum(*)` fingerprints matched the
pre-vintage warehouse exactly, `forecast_history` included — which is the
stronger of the two results, because that file is not restored from git on the
way home but recomputed by `backtest.py` from current silver. The Python half
of the chain is deterministic to the byte. A second round trip, to 6 August,
reproduced the same fingerprints again.

**The gate's refusal was then exercised for real**, not only as a replayed
case. It matters that the warehouse was in a state where the gate already had
something to say: on current data it returns `ingest_not_run`, the last ingest
being 88 hours old. With the 6 August vintage loaded the verdict became
`warehouse_is_vintage`, naming the date and the command that undoes it, and
after the return it went back to `ingest_not_run`. So the check does not merely
fire — it *precedes* a check that was already firing, which is the only
ordering that is safe. A vintage warehouse on a week with fresh data would
otherwise have passed everything.

### The risk this design accepts

Silver and gold are overwritten in place, so between entering a vintage and
returning, the warehouse genuinely holds vintage numbers, and **nothing detects
that state**: the freshness gate compares bronze against
`pipeline.processed_weeks`, and a vintage run moves neither. The mitigation is
that entry and return are documented as one operation rather than two, and the
exposure is bounded by every weekly run rebuilding everything anyway. Report 1
is insulated by being an Import model refreshed by an explicit step — vintage
numbers cannot reach the published link unless a human refreshes while in that
state, and the report would then show an earlier maximum week, which is a
visible error rather than a silent one.

Setting `as_of_vintage` and `simulate_cutoff_date` together raises a
compilation error. The composition has no reading: weeks up to one date,
valued as at another.


**Stack question, explicitly undecided:** whether to keep building on
Azure/Fabric or move new work (starting with the margin analysis in the
research backlog, `docs/workstreams.md`) to
a GCP-based stack (BigQuery/DuckDB + Looker Studio) was raised and
deliberately left open rather than decided. Abandoning Azure mid-series
would also abandon the project's original stated goal (comparing the
GCP-familiar author's experience against Microsoft's stack) and a fair
amount of working, verified infrastructure. Current lean: keep the
oil-price work on Fabric as already built; if a new stack gets tried, do
it on the *next* new direction (margin analysis) rather than migrating
what already works.

**The always-on argument that used to sit here was wrong — corrected 11
Aug 2026.** This section previously claimed that Fabric *requires* capacity
to stay running for anyone to view a published Power BI report, and scored
that as a real point in GCP's favour. That is true only for a workspace
backed by an F capacity, which is how this project happened to be set up —
it is not a property of Power BI. Verified empirically:

- Report 1's semantic model and report were republished to **My Workspace**
  (shared capacity, not the F2) and shared via **Publish to web**.
- With `nzfuelcapacity` in state `Paused` for 70 minutes — well past the
  one-hour publish-to-web cache — the report rendered with data.
- Cost to serve it: zero. F2 is now only needed for the weekly `dbt run`.
- New public URL is on `app.powerbi.com`, not `app.fabric.microsoft.com`;
  the old Fabric-workspace embed code is dead and should be deleted from
  Settings → Manage embed codes. **It wasn't** — that deletion was left
  undone until 13 Aug 2026, and the live second public link it left behind
  caused real confusion; see "Two models named `nz_fuel`" above.

Two related facts worth keeping: **F2 never bought viewer-licensing
relief** — free viewers on capacity-backed workspaces start at F64 — and
publish-to-web requires **import** mode (DirectQuery and live connections
are unsupported), model and report in the **same** workspace, and no
report-level DAX measures.

**Still open:** the account is 46 days from the end of a Power BI Pro trial
(ends ~26 Sep 2026). Whether publish-to-web from My Workspace survives on a
Free licence is unresolved — Microsoft's docs point both ways (the
publish-to-web page lists My Workspace as needing only "a Microsoft Power
BI license", while the licence-comparison page says Free users cannot use
sharing features). Graph reports the assigned licence as
`POWER_BI_STANDARD` / `BI_AZURE_P0` with no Pro SKU in the tenant, so the
trial appears to be tracked inside Power BI rather than in Entra. Check the
public link the day after the trial ends; fall back to Pro (~NZ$24/mo) or
PDF if it breaks.

## The T-SQL lag layer — deleted 8 Sep 2026, design kept

The four models documented below — `lag_correlation`, `lag_resolved`,
`factor_volatility` and `volatility_config` — were this project's first
implementation of its own question, a direct port of the original R script into
T-SQL. They fed the first Report 1: `resolved_lag` and `resolved_slope` drove
the forecast, `factor_volatility` against `calm_baseline` drove the "is a crisis
still happening" indicator.

**Nothing read them by the end.** The published model `nz_fuel_v2` holds one
table, `forecast_accuracy`, built from what `backtest.py` and
`build_period_flags.py` write; no `ref()` in it reached silver or any model
below. Checked twice — 3 Sep 2026 across `models/`, `research/`, `pipeline/`
and the `.tmdl`, and again on 8 Sep before deleting. The second check found
`lag_correlation` read only by `lag_resolved`, its own sibling, and the four
mentioned in `analyses/` only in comments. Until 8 Sep every weekly
`dbt run --full-refresh` built all four.

Three measurements retired them, in this order, all recorded in
`docs/research.md`: single-best-lag is weakly identified, because the lag
profile is a broad hill and the winner's margin sits in the third decimal; the
correlation is fitted on levels while the forecast multiplies a *change*, which
inflates the slope by about 70%; and the walk-forward test puts the resulting
formula behind "the price won't move" at one and two weeks. Report 1 was rebuilt
on the Python ADL+ECM, and these four were left running without a consumer
rather than deliberately retired.

**Decided 8 Sep 2026: deleted**, along with `macros/lag_correlation_series.sql`,
whose only caller was `lag_correlation`, and the `volatility_window_weeks` var.
`periods.csv` survives — `export_panel.py` reads it.

The argument was not cost. All four rebuild in about 14 seconds, roughly a
third of a cent of F2 per week; that is not worth a decision. It was that they
carried **22 of the project's 65 data tests**. `dbt test` is step 4 of the
weekly chain and any failure outside `monitoring` stops it, so a third of the
test suite could halt the publication of a report that does not depend on a
single one of those tables. Unscheduling would have kept that liability in a
worse form — a model nobody builds is a model nobody notices breaking, and
"left running without a consumer" is the state that produced this section in
the first place.

**What was given up, stated precisely.** Not the volatility signal —
`crude_vol_regime` in `build_period_flags.py` measures the same thing better:
log changes rather than percentage changes, so it does not drift with the
level; a 9-week window with hysteresis (enter at p92, stay to p85, discard runs
under four weeks) rather than one number compared against a threshold, so a
single quiet week cannot split an episode; and full-sample percentiles rather
than `calm_baseline`, which was derived from hand-drawn `calm` periods and so
was mildly circular. What was given up is the *trailing* computation:
`factor_volatility`'s window ended on the current week, while
`crude_vol_regime`'s is centred and marks its own last four weeks
`crude_vol_window_full = False`. A live indicator therefore needs a trailing
re-derivation — which `build_period_flags.py` already prescribes in a comment,
and which is `center=False` on the same log-change series. Nothing in Report 1's
spec asks for one.

What follows is the design of those four. It is kept because it is the
reasoning any replacement would have to answer, not because it describes
anything currently in use.

## Lag correlation — matching the original R methodology, not a shortcut

Fabric Warehouse (T-SQL) has no built-in `CORR()`. `macros/lag_correlation_series.sql`
computes Pearson's r manually from raw sums (`ΣX`, `ΣY`, `ΣXY`, `ΣX²`, `ΣY²`)
per lag, which also matches what the original R script did deliberately —
R's own `ccf()` normalizes across the whole series regardless of lag, which
gave different (wrong, for this use case) results on short windows.

Two guards, both `NULL`, not errors:
- fewer than 3 paired points at a given lag
- zero variance in either series at that lag (division by zero otherwise)

**T-SQL quirk hit here:** `WITH` (a CTE) must be the first statement in a
batch — it can't appear inside a `UNION ALL` block. The macro is written with
nested derived-table subqueries instead of CTEs for this reason.

## Dynamic max-lag cap per period

`max_lag = min(10, floor(period_weeks / 3))`, calculated per period, not a
flat constant. A short period (e.g. the 2025 tariff shock, ~13 weeks) capped
at a flat 10 was overfitting — the "best" lag kept landing on the edge of
the tested range with a correlation that was really just noise from too few
data points. Once capped at `floor(13/3) = 4`, the artificially strong
correlation (r ≈ 0.65–0.87 at lag 9) collapsed to what it actually was
(r ≈ 0.04–0.07 at lag 4) — same rule the original R script used.

## Edge-guard (`lag_resolved`)

Even with the dynamic cap, a period's best-correlated lag can still land
exactly on the tested boundary. `lag_resolved` flags this
(`is_edge_artifact`) when the best lag equals the period's max tested lag
*and* correlation was still rising going into that boundary (i.e. r at the
edge > r one lag before it) — a sign the true peak is probably outside the
tested range, not a genuine result. Flagged rows fall back to lag=0 rather
than reporting a number that's an artifact of where the search stopped.

This isn't cosmetic: for `exchange_rate` in `03_ukraine_2022` and
`04_tariff_2025`, the artifact-flagged raw correlation was weakly positive,
but the resolved (lag=0) correlation is strongly negative (~-0.8) — which
matches the expected direction (a weaker NZD should mean a higher landed
cost, once you're not comparing the wrong lag). The guard didn't just clean
up noise, it recovered the theoretically-expected sign.

## Factor and target are both dimensions, not fixed choices

`lag_correlation` tests three factors (`dubai_crude_usd`, `dubai_crude_nzd`,
`exchange_rate`) against two targets (`board_price`, `adjusted_retail_price`),
not one hardcoded pair. The reasoning for each dimension:

- **`dubai_crude_nzd`** already embeds the exchange rate (it's USD price ÷
  NZD/USD rate). Testing it alongside `dubai_crude_usd` +
  `exchange_rate` separately isn't redundant — NZD is the single number that
  reproduces the original R analysis exactly (see below), while USD +
  exchange rate tested separately is the only way to *attribute* an effect
  to oil price versus currency movement rather than just observe their
  combined impact.
- **`board_price`** (the retailer's posted price) decomposes cleanly via
  MBIE's own identity (`Board price = Importer cost + Taxes + GST + ETS +
  Importer margin`), making it the cleaner variable for understanding the
  cost pass-through *mechanism*. **`adjusted_retail_price`** (what people
  actually pay, net of loyalty/discount schemes) is the more honest variable
  for "what does this mean for someone filling up," at the cost of adding
  retailer-side noise unrelated to cost pass-through. Neither is strictly
  correct — they answer different questions, so both are computed.

## Bug: target wasn't bounded by the period, factor was

`lag_correlation` originally filtered the *factor* series to the period's
date range before joining, but not the *target* series — the target
subquery only filtered on `Fuel`. At lag 0 this made no difference (the join
naturally stays inside the period). At larger lags, shifting a factor date
forward could land past the period's end date, silently joining against
target rows from the *next* period.

This wasn't caught by any test — `n` per lag stayed exactly right (34 for
every lag in the affected period), because the leak doesn't create or drop
rows, it just joins the wrong ones. It only surfaced by validating gold
output against the original R script's printed correlation tables: one
period (`05_calm_import_era`, which sits immediately before the ongoing
2026 crisis) had a correlation profile with the opposite sign and shape from
R's. R bounds both series to the period before computing anything, so it
can't leak across a boundary by construction; the SQL version had to be
fixed to bound the target subquery by the same `period_start`/`period_end`
as the factor.

**Lesson:** re-deriving a validated R script's logic in SQL needs the same
validation step it started with — line up final numbers against the
original before trusting the port, not just checking the SQL runs without
error. A silent join leak that keeps row counts exactly right is invisible
to schema tests; it's only caught by checking output values against a
trusted reference.

## "Is a crisis still happening?" — why this became a continuous indicator, not a yes/no flag

Report 1 (the "should I fill up now" dashboard) needs to know whether the
historical crisis-lag pattern still applies *today*. The 6 periods in
`seeds/periods.csv` were labeled by eye — start dates are reliable (each one
is pinned to a specific news event: invasion, tariffs, etc.), but end dates
were a judgment call based on looking at the oil price chart. That's fine
for retrospective analysis, but it can't be automated for a live, daily
report — there's no future data to eyeball yet.

**First idea — a volatility threshold, checked**, not assumed. Computed
rolling `STDEV` of `dubai_crude_nzd` week-over-week % change over a moving
window, compared against a calm-period baseline (`stdev` over the full
`02_calm_own_refinery` and `05_calm_import_era` periods: 0.0302 and 0.0268
respectively — so a real baseline of roughly 0.027–0.030, not a guessed
number).

**Tested against all 3 closed crisis periods (COVID, Ukraine, tariff
shock)** before trusting it. Two things fell out of that:
- Short windows (4 weeks) react fast to the *start* of a shock but are
  noisy — they can dip back near calm-baseline for a week or two in the
  *middle* of an ongoing crisis (seen clearly in the Ukraine period,
  mid-May 2022), which would cause Report 1 to falsely signal "crisis over."
- Long windows (8–10 weeks) are stable but structurally *lag* the real end
  of a crisis by nearly the window's own length, because they keep
  "remembering" old high-volatility weeks long after the raw weekly changes
  have actually calmed down.

**Tried a binary rule instead** — "3 consecutive weeks with `|pct_change| <
0.03`" — tested against the same 3 periods. It didn't fire reliably: it
never fired at all within ~6 weeks of the labeled end of COVID, and fired
2.5 weeks late for Ukraine and *almost 2 months* late for the tariff shock.
Looking at the raw weekly changes around each labeled end date explains why:
volatility doesn't switch off, it decays with occasional relapses — a rule
requiring a clean run of calm weeks will always find a later, stricter
"end" than what a human sees as a declining trend.

**Decision: no binary trigger.** Report 1 shows a continuous measure
(`% above calm baseline`) plus a trend direction (easing / intensifying),
rather than pretending there's a precise date on which a crisis regime
switches off. This is consistent with the rest of the project's stance on
honest uncertainty (edge-guard, the forecast confidence tiers) — a fabricated
yes/no answer here would be less honest than the data supports, not more
useful.

**Known limitation, deliberately out of scope for now:** this whole problem
— objectively dating regime start/end from a time series — is a real,
established field (Markov regime-switching models, going back to Hamilton
1989; the simpler Bry-Boschan peak/trough algorithm used by NBER for
recession dating). A Markov-switching model has even been applied
specifically to currency crisis prediction (Abiad, IMF 2007), which matters
here since exchange-rate "crisis periods" won't line up with oil-price ones
if that factor is ever analyzed with the same rigor. Worth revisiting with
a proper model in R/Python rather than hand-rolled SQL heuristics if this
project's forecasting ambitions grow — the rolling-volatility approach above
is a pragmatic bridge, not a claim to have solved regime detection.

## `volatility_config`: one source of truth for window size and calm baseline

Originally `factor_volatility` computed and duplicated `calm_baseline` on
every row, and the window size (`rows between N preceding`) was a Jinja
literal baked into that one model. Split into a separate one-row model,
`volatility_config` (`window_weeks`, `window_days`, `calm_baseline`), read
by both dbt (`factor_volatility`) and Power BI (DAX measures) via
`ref()`/`MAX()` respectively. Changing `volatility_window_weeks` in one
place (a dbt var) now propagates everywhere after `dbt run` + Power BI
refresh — no hunting for a hardcoded `21` or `0.0285` in a DAX formula.

That gap was found the hard way: the first version of the `Volatility
Trend` DAX measure had `21` (3 weeks) hardcoded twice, independent of the
6-week window actually configured. Doubling the window later wouldn't have
changed the trend comparison at all without a second, easy-to-forget manual
edit.

## Slope, not just r — and the forecast's honest limits

> **The forecast formula described here was measured on 15 Aug 2026 and
> lost to doing nothing; note added 3 Sep.** Walk-forward, refitting at
> every cutoff over 703 weeks, a reconstruction of it runs 26% worse than
> "the price won't move" at one week, level-pegs at two, and beats naive in
> 39% of weeks — see "Walk-forward test" in `docs/research.md`, including why a
> period-conditioned measure cannot be backtested honestly at all. The
> slope arithmetic, the confidence tiers and the lag-0 edge case below are
> unaffected and still describe what is deployed; the claim that the
> formula forecasts anything is not.

`lag_correlation_series` also returns `slope` (`(nΣXY − ΣXΣY) / (nΣX² −
(ΣX)²)`, the same regression-line slope, reusing sums already computed for
r), carried through `lag_resolved` as `resolved_slope` (falling back to the
lag-0 value under the same edge-guard logic as `resolved_r`). `r` says how
tightly two series move together; `slope` says by how much — cents per
litre per NZD/barrel of crude. Both are needed: a forecast can't be built
from correlation strength alone.

**Forecast formula:** `forecast = current_price + resolved_slope × (crude_now
− crude_lag_weeks_ago)`, using the raw NZD-denominated crude price and each
fuel's own `resolved_lag` — not a fixed window borrowed from the volatility
indicator (an early draft mistakenly used `volatility_config[window_days]`
here; the two windows serve unrelated purposes and shouldn't share a
number).

**Confidence tiers**, from `resolved_r` (not arbitrary — Cohen's *r* ≈ 0.5
is a widely-cited "large effect" threshold; several other frameworks put it
at "moderate," not "strong," so the stricter 3-tier split was chosen
deliberately over a single cutoff): `|r| ≥ 0.7` → Strong, `0.5–0.7` →
Moderate, `< 0.5` → forecast withheld entirely rather than shown with a
caveat. Showing a number with a disclaimer is easy to skim past; not
showing one at all is the honest version of "we don't know."

**Known edge case: `resolved_lag = 0`.** The forecast formula is
structurally meaningless here — "change in crude over the last 0 weeks" is
0 by construction, so the whole forecast collapses to 0% regardless of
actual conditions. `lag = 0` is a real, valid finding (same-week
pass-through), just not one this particular forward-looking formula can
use. `Forecast Display` needs to special-case it explicitly rather than
silently reporting a meaningless 0%.
