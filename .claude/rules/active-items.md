# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

- [ ] **~mid-Oct 2026** — Stats NZ releases the September-quarter CPI, and
  MBIE finalises the thirteen weeks of Jul–Sep 2026. This is the second
  observation of an event the project has now seen once, and the first it
  can prepare for. Two things to check, both cheap and offline:
  - **Does the finalisation move anything but the quarterly factor?** On
    26 Aug it did not, but that release also carried unrelated revisions, so
    one observation cannot separate "a finalisation" from "a release
    containing one". Q3 currently carries Q2's factor (diesel 2.847, petrol
    3.746) and will shift by whatever the new one differs by — historically
    nothing to ±3.6 c/L.
  - **Re-run `research/headline_results.py`.** Thirteen more Final weeks
    will enter the sample. Last time that reversed a diesel result and
    removed a petrol one; the numbers in `docs/research.md` are written
    against 29 Aug 2026 and will need the same treatment again.
  Method and expectations: `docs/mbie_notes.md`, "A standing prediction".

- [x] **The chain past the gate ran green in CI, end to end, 10 Sep 2026.**
  Run 34425310513: `aip`, `snapshot`, `build`, `test`, `panel`, `flags`,
  `backtest`, `report`, `close` all passed, the capacity paused itself, and
  `close` recorded `2026-09-04` processed at 35,040 bronze rows. `flags` and
  `backtest` wrote to the database from CI for the first time. Delete this
  once one more weekly run has gone through unattended.
  - It took two attempts. The first, 34424785517, stopped at `snapshot`:
    `dbt_packages/` is gitignored, nothing in the workflow ran `dbt deps`,
    and every dbt command failed on "expects 1 package(s) ... found only 0".
    Invisible locally, where the directory has been on disk since July. Fixed
    the same day — `task deps`, beside the other install steps.
  - **`aip` warned and carried on, and that was a whole component producing
    nothing.** `could not fetch the FX series (The read operation timed out);
    store left unchanged`, then 18 Diesel and 14 Regular Petrol reports
    downloaded and thrown away with the runner. **Settled and fixed the same
    day** — measured from a runner, `fredgraph.csv` times out under urllib
    while curl fetches it in 2.9 s and the FRED API answers urllib in 0.2 s;
    Yahoo, the fallback we would have reached for, returns HTTP 429 from
    GitHub egress. `aip_check.py` now uses the API with `FRED_API_KEY`, and
    prices each week on its own Mon–Fri rather than on the last five rows of
    whatever the series happens to hold. Written up in `docs/architecture.md`,
    "The FX half, and two ways it was wrong".
    - **Not yet exercised by a real weekly run.** Verified from a runner over
      synthetic weeks (probe run 34434860722) and locally on the cached PDFs,
      but `task aip` itself has not gone through since the change. The store's
      newest week is **2026-08-28** — read from the warehouse, not inferred
      from the newest cached PDF, whose 30 Aug filename is its publication
      date and carries the week to Friday 28 Aug. The next scheduled run should
      close that by itself: CI re-downloads every report on the AIP site each
      time and `append_new` inserts whatever is missing, so 6 Sep and 13 Sep
      come in together. Delete `.github/workflows/fred-probe.yml` once that
      has happened.
    - **Week 2026-09-04 was cross-checked by hand instead, and agrees.** Done
      offline on 10 Sep 2026 with `monitor_aip_gap`'s arithmetic: the AIP
      side from the week-to-4-Sep reports (now in the local PDF cache) and
      FRED, our side from the MBIE file downloaded through Chrome that
      morning. Nothing written to the store.

      | week-on-week, USD/bbl | ours | Argus | ours / Argus |
      |---|---|---|---|
      | Diesel | +11.25 | +11.10 | 101% |
      | Regular Petrol | +9.38 | +9.56 | 98% |

      A flag needs ours under 25% of theirs. The markup held week to week —
      diesel 14.42 → 14.57, petrol 10.40 → 10.23 USD/bbl — but both now sit
      above the ranges `architecture.md` records for Oct 2025 – Aug 2026
      (6.9–13.4 and 7.4–9.6). Worth updating those once a few more weeks
      confirm it is a level and not a spike.

      The week itself: importer cost jumped (diesel +14.12, petrol
      +11.61 c/L), pump prices fell about 1.2 c/L, and importer margin took the
      whole move (−15.09, −12.58) — around the 98th percentile of weekly
      margin changes by size over all 1168 weeks. Margins are at the 5th–6th
      percentile of the last five years but the 42nd–46th of the full history,
      so "a low for recent years", not "a historic low". Provisional; MBIE
      had already revised 28 Aug between 7 and 10 Sep (petrol importer cost
      +0.43 c/L).
  - **The federated identity credential is pinned to `refs/heads/main`.** A
    workflow run from any other ref fails at `azure/login` with AADSTS700213
    before reaching the capacity, so a CI change cannot be tested on a branch
    — it has to be merged first. Verified on run 34424623434, which cost
    nothing because every step after login was skipped.

- [x] **The chain past the gate had never run in CI — closed 10 Sep 2026.** Every grant is in place and a full manual run went green on
  8 Sep 2026, but the gate answered `nothing_new` and everything after it was
  skipped. The 10 Sep publication was meant to be the first real exercise of
  `aip`, `snapshot`, `build`, `test`, `panel`, `flags`, `backtest`, `report`
  and `close` on a runner. **It was not**, for two separate reasons, both
  worth keeping:
  - **The schedule misfired.** `Weekly load` fired 110 minutes late (slot
    21:00 UTC, run `34414150430` created 22:50:13 UTC) and the watchdog's
    21:30 slot had still produced no run at 23:04 UTC — 94 minutes, less
    than the delay the load itself turned out to have, so whether it was
    lost or merely late is not established. Nothing alerted either way; it
    was noticed by hand. This is what W16 in `docs/workstreams.md` now exists to fix.
  - **The gate then refused, and was right to.** Verdict
    `ingest_did_not_land`: the Copy activity reported reading **35040** rows
    while bronze held **35010** — exactly the marker's `ingest_rows_read`
    from the previous week — with `bronze_week` still `2026-08-28`, equal to
    `last_processed_week`. So the source did grow by what looks like one
    week (+30 rows), and bronze did not receive it. Steps after the gate were
    skipped and `capacity-pause` ran; the capacity was verified `Paused`
    afterwards, so nothing was left billing.

    **The source was checked directly and is not the problem.** The file was
    downloaded through Chrome on 10 Sep 2026 at 11:06 NZT — Imperva still
    refuses every non-browser client, so this cannot be scripted — with a
    `?cb=` cache-buster to reach origin rather than the week-behind edge.
    2,883,540 bytes, **35040 data rows**, 1168 weeks, 2004-04-23 through
    **2026-09-04**, a uniform 30 rows per week. So the Copy activity's
    reported `rows_read` is corroborated exactly: MBIE did publish week
    2026-09-04, and the activity did read the whole file.

    **What bronze holds is the file minus exactly its newest week.**
    35040 − 30 = 35010, which is bronze's count to the row, and bronze's
    newest week is `2026-08-28`, the one before. Bronze is therefore not a
    partial write that happened to stop somewhere — it is precisely the
    previous week's state, which is the signature of reading a **stale
    snapshot**, not of a failed load. The ingest reported finished at
    22:52:33 UTC and the gate queried at 22:52:54, 21 seconds later; a
    Lakehouse SQL analytics endpoint is known to serve stale metadata for a
    period after a write, and `refresh_sql_endpoint_metadata` exists for
    exactly that.

    **Read on 10 Sep 2026 by waking the capacity. Half settled.** Bronze
    still read 35010 rows and week `2026-08-28` at **25 minutes** after the
    write — the copy activity finished at 22:52:28 UTC and the re-read was
    at 23:17 UTC. Twenty-five minutes is not long enough to distinguish a
    stuck endpoint sync from a slow one, so the *reason* remains open. The
    copy activity's own detail, however, says the write itself succeeded in
    full:

    ```
    status        Succeeded        errors        []
    dataRead      2883540          rowsRead      35040
    dataWritten   345981           rowsCopied    35040
    filesWritten  1                sink          bronze_lakehouse.mbie.weekly_prices
    ```

    `dataRead` is byte-for-byte the file downloaded through Chrome, so the
    source read is independently confirmed by two routes, and `rowsCopied`
    says all 35040 rows were written to the right table. **So the load did
    land in the Lakehouse table; what is behind is the SQL analytics
    endpoint**, which both the gate at 26 seconds and the re-read at 25
    minutes saw in its pre-write state.

    **Root cause, settled 10 Sep 2026. Nothing broke — automation removed a
    delay a human used to supply.**

    The Delta commit is independently confirmed: `_delta_log/…022.json` and
    `…023.json` are timestamped 22:52:25 and 22:52:26 UTC, and the parquet
    beside them is 345,981 bytes, matching the activity's `dataWritten` to
    the byte. The data was in the Lakehouse table from that second. What
    lags is only the SQL analytics endpoint: stale at 21 minutes, fresh by
    52.

    **The loader has not changed at all.** Sink configuration is identical
    across every run back to 13 Aug — `tableActionOption: OverwriteSchema`,
    `partitionOption: None`, `applyVOrder: false` — so the 27 Aug
    `updateDefinition` did not alter it, and `OverwriteSchema` is not new.
    `rowsRead` equals `rowsCopied` in every run and climbs by exactly 30 a
    week: 34920, 34950, 34980, 35010, 35040. The cache-buster reaches origin
    as designed.

    **What changed is when the gate is asked.** From `pipeline.processed_weeks`,
    against the copy time of the same week:

    | week | copy finished | gate succeeded | gap |
    |---|---|---|---|
    | 2026-08-21 | 22:03:50 | 22:53:29 | **50 min** |
    | 2026-08-28 | 05:24:39 | 05:55:40 | **31 min** |
    | 2026-09-04 | 22:52:26 | — (failed) | **26 sec** |

    Every successful week was gated half an hour to an hour after the
    ingest, by a human working inside a long capacity session. CI asks at 26
    seconds and pauses the capacity about a minute later, so the endpoint's
    background sync never gets the window it used to get for free. The 3 Sep
    occurrence fits exactly: the first attempt failed, and the retry 31
    minutes later succeeded.

    **Consequence.** The fix is not in the loader and not in the gate's
    logic — the gate reported correctly on what it was given. Between the
    ingest and the gate the chain has to make the endpoint current, and
    `refresh_sql_endpoint_metadata` forces that sync rather than waiting for
    it. Simply waiting also works but bills the capacity for the wait —
    roughly 30 minutes a week, about NZ$0.36, some NZ$19 a year — and is
    hostage to a duration nothing documents.

    **Measured 10 Sep 2026 with a disposable probe, and the fix is
    confirmed.** A copy pipeline identical to the production one — same HTTP
    source, same `LakehouseTableSink`, same `OverwriteSchema` — was pointed
    at `bronze_lakehouse.probe.sync_probe` with an extra `probe_stamp`
    column carrying `@utcnow()`, so two otherwise identical runs could be
    told apart. Production data was never touched; both the probe pipeline
    and the probe table were deleted afterwards.

    | | |
    |---|---|
    | new table written 00:15:33 | invisible to T-SQL at 19 s, 1.5 min, 3.7 min, **8 min** |
    | `refreshMetadata` at 00:23:53 | Succeeded in **7 s**; table visible at 00:24:12 |
    | same table overwritten 00:25:17 | endpoint still served the **previous** stamp 8 s later |
    | `refreshMetadata` at 00:25:37 | Succeeded in **6 s**; new stamp visible at 00:25:48 |

    So both shapes reproduce — a table that does not appear at all, and a
    table whose contents are a version behind — and one forced refresh cures
    either in under ten seconds. Eight minutes was not the ceiling; nothing
    says what is.

    **Written 10 Sep 2026 on branch `fix/endpoint-sync-in-ingest`, and not
    yet run.** `run_ingest.py` calls `fabric_io.refresh_sql_endpoint()` as its
    last act; `task sync-endpoint` and `--sync-only` cover the `skip_ingest`
    path, and `weekly.yml` calls that task when the copy is skipped. Syntax
    checks pass and `task --list` parses, but **nothing has executed yet**.
    (The venv is one level above the dbt project, `$PWD/../.venv`, exactly as
    `Taskfile.yml` documents — looking for `.venv` inside the project and
    concluding there is none is a mistake worth not repeating.)

    **The fix.** Force the sync between `ingest` and `gate`:
    `POST /v1/workspaces/{ws}/sqlEndpoints/{id}/refreshMetadata?preview=true`
    — asynchronous, poll the `Location` header to `Succeeded`. The endpoint
    id for `bronze_lakehouse` is `a2abcf3b-c492-42ca-aa16-3bac2db77a37`.
    Note the MCP server runs with `FABRIC_MCP_READONLY`, so this call cannot
    go through it and belongs in `fabric_io.py` beside the other REST calls.
    Six seconds a week against roughly NZ$19 a year of waiting, and it does
    not depend on a duration nobody documents.

    **`snapshots/mbie_revisions.sql` needs it as much as the gate does.**
    Those two are the only readers of `source('bronze', …)`; everything after
    the snapshot is warehouse-internal and cannot see this. A gate that
    passed on a stale endpoint would hand the same stale rows to
    `dbt snapshot`, which would record nothing and stay green.

    **Bronze is current as of 10 Sep 2026 11:44 NZT**: 35040 rows, newest
    week `2026-09-04`. The week is no longer stuck; the chain has not been
    re-run.
  - `flags` and `backtest` now write to the database from CI, which has never
    happened from anywhere but this laptop.
  - The Power BI refresh stays manual until W9.

- [x] **Budget alert in Cost Management — exists, verified 8 Sep 2026.**
  `nz-fuel-price-budget`: NZ$20/month, whole subscription, monthly reset,
  running to 30 Jun 2028, with actual-spend alerts at 50/100/150/200%. Current
  month NZ$1.14. This replaces the spending limit that the 3 Sep pay-as-you-go
  upgrade removed; the 23:00 NZT auto-pause is the other guard.
  - **The alerts go only to `morozov_77@hotmail.com`**, the billing Microsoft
    Account — not to `andrei@…onmicrosoft.com`, which is the account the
    project is normally driven from. An alert nobody reads is not a guard, so
    either that mailbox gets watched or a second contact goes on the budget.
  - All four thresholds are **Actual**, not Forecasted, so the first warning
    arrives after NZ$10 is already spent. At NZ$17.50/day for a capacity left
    running, that is about half a day of drift. A forecasted threshold would
    warn earlier; not added, because the auto-pause is meant to make that case
    impossible and adding one would be guarding against the guard.

- [x] **`nz_fuel_v2` republished from Desktop, 10 Sep 2026 — and the question
  it left open is now answered.** Four columns left `forecast_accuracy` on
  7 Sep (`pred_report1_ish`, `abs_err_report1`, `mae_report1_26w`,
  `skill_report1_26w`, after `report1_ish` was withdrawn from the backtest).
  This note used to say that whether a refresh of the stale model would fail
  was untested. **It fails.** A service refresh was attempted on 10 Sep and
  ended `Failed` in 16 seconds with
  `ModelRefresh_ShortMessage_ProcessingError: The 'pred_report1_ish' column
  does not exist in the rowset`.

  **So the order is not a preference, it is a requirement: republish first,
  refresh second.** Removing a column from a model's source table breaks the
  next refresh of the deployed model, whether or not any visual read it — the
  partition query names every declared column. The same applies to a rename.

  Doing it from Desktop takes about five minutes: open the report, resume the
  capacity, refresh schema and data, publish, pause the capacity. Verified
  afterwards from here — capacity `Paused`, and a DAX probe against the model
  returned 6,390 rows with `max week_date` 2026-09-04, against 6,381 and
  2026-08-28 before. Delete this note once one more weekly refresh has gone
  through.
  - **The deployed model had drifted from git, unrecorded.** Its measure was
    named `26-Week Windows Ahead %` while `pbip/` has carried
    `Weeks Model Ahead %` since 16 Aug 2026; the old name appears nowhere in
    the history, so it was renamed in the service or in a Desktop session
    whose pbip was never saved back. Found while diffing the deployed
    definition, not by anything watching for it.

    **The 10 Sep republish did not close it**, checked afterwards by reading
    the deployed definition back: the four dead columns are gone (Desktop's
    "refresh schema" dropped them), but the measure is still
    `26-Week Windows Ahead %`. So the file Desktop publishes from is its own
    copy, not the `pbip/` in this repository, and the two have diverged at
    least on this name. Which one is the source of truth has to be decided
    in Desktop — either save the pbip back into the repo or open the repo's
    pbip there. Until then, a change committed to `pbip/` does not reach the
    published model, and nothing reports that it has not.
- [x] **`forecast_accuracy.sql` compiled and ran against the warehouse,
  10 Sep 2026.** `dbt run --select forecast_accuracy --full-refresh` inside
  run 34425310513: `PASS=1 WARN=0 ERROR=0`. The edit that removed three
  expressions and one CTE column is confirmed good. Delete this note.

- [x] **Republish `nz_fuel_v2` before the next refresh — done 3 Sep 2026**,
  ahead of the week 2026-08-28 refresh. The deployed model had declared
  `flag_data_status` since 27 Aug (W14) while the table no longer had the
  column, and the partition pulls the whole table, so a refresh of the stale
  model would have failed. Delete this once one more weekly refresh has gone
  through cleanly.
  - **Publishing from Desktop threw** `Cannot perform interop call to:
    MinervaDialog.onHtmlDocumentLoaded — object with this Id is not
    registered` — a .NET unhandled-exception box, not a model or data error.
    It is Desktop's dialog failing to render in its embedded WebView2 control.
    The publish went through anyway. If it recurs and does not: restart
    Desktop, check File → Account, repair the Edge WebView2 Runtime, or skip
    the dialog entirely by saving a `.pbix` and using My Workspace → Upload.

- [x] **27 Aug 2026 — the Azure free-trial credit expired, and it stopped
  everything.** Resolved 3 Sep; delete once the budget alert above exists.
  What actually happened, because the note above had predicted the cost and
  not the mechanism: the spending limit turned the subscription **read-only**
  and Azure suspended resources inside it. `az … --action resume` on the
  capacity returned `ReadOnlyDisabledSubscription`, and
  `auto-pause-fabric-capacity` was found `Suspended` — so the one remaining
  guard had been switched off by the same event, silently.
  - **Only the billing administrator can upgrade**, and it is not the account
    this project is normally driven from. `andrei@…onmicrosoft.com` is
    Contributor + Cost Management Reader and gets "ask your billing
    administrator"; the Owner and signup identity is the Microsoft Account
    `morozov_77@hotmail.com`. Sign in as that one for billing, everything else
    under the usual account.
  - **ARM lags the upgrade.** Through the whole ~30-minute weekly run the
    subscription still read `state: Disabled`,
    `quotaId: FreeTrial_2014-09-01`, `spendingLimit: On` while every write
    went through fine; it read `Enabled` / `PayAsYouGo_2014-09-01` /
    `spendingLimit: Off` shortly after. Test with a write, not a read — the
    metadata is not the truth here.
  - `auto-pause-fabric-capacity` came back to `Enabled` on its own when the
    subscription was re-enabled. Worth re-checking rather than assuming, since
    it is now the only automatic guard.

- [ ] **~27 Sep 2026** — the Power BI Pro trial ends ~26 Sep. The day
  after, open Report 1's public link and check it still renders with data.
  Report 1 is now served via Publish to web from **My Workspace** and costs
  nothing, but it is unresolved whether that survives on a Free licence —
  Microsoft's docs point both ways. If it breaks: Pro (~NZ$24/mo), or back
  to PDF. Details in `docs/architecture.md` (Stack question) and
  `docs/cost_notes.md`.
