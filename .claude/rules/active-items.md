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

- [ ] **Next weekly load (~17 Sep 2026) — expect zero `final_rewritten`.**
  MBIE's 3 Sep release cut `Value` to ~10 significant digits and switched
  `Date` to DD/MM/YYYY; the 10 Sep release put both back. Each flip wrote
  15,848 noise versions into the snapshot. If the next load shows
  `final_rewritten` in the thousands again, the precision is flipping as a
  habit, and the snapshot should compare on `ROUND(TRY_CAST(Value AS float), 4)`
  rather than `Value` — measured, and written up, in `docs/mbie_notes.md`
  under "Known structural changes", 3 and 10 Sep. If it is zero, delete this.
  Query: `select detected_on, revision_class, count(*) from
  monitoring.monitor_revisions where detected_on >= '2026-09-15' group by
  detected_on, revision_class`.

- [ ] **AIP markup sits above the range `architecture.md` records.** From the
  hand cross-check of week 2026-09-04, done offline on 10 Sep 2026: diesel
  14.42 → 14.57 and petrol 10.40 → 10.23 USD/bbl over MBIE's importer cost,
  against the Oct 2025 – Aug 2026 ranges of 6.9–13.4 and 7.4–9.6. The markup
  held week to week, so this is not a one-week spike, but two weeks is not a
  level either. Both sides now have weeks to 4 and 11 Sep in the store, so
  `monitor_aip_gap` can answer it — a warehouse read, therefore not free. If
  the newer weeks agree, update the ranges in `architecture.md` rather than
  leave the comparison anchored to a year that has ended.

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

    The 10 Sep republish did not close it on its own: the four dead columns
    went (Desktop's "refresh schema" dropped them), but the name stayed, so
    Desktop publishes from its own copy, not from this repository's `pbip/`.

    **Closed the same day, for this divergence only, by taking Desktop's
    version** — a call about the situation, not a standing rule; the manual
    publish step is due to go with automatic refresh, which is its own piece
    of work. `pbip/` was brought into line by pulling both definitions back
    from the service with
    Fabric `getDefinition` — it works on My Workspace and with the capacity
    paused — and taking what Desktop had changed: the measure name, in the
    model and in visual `c4ahead`, and two reworded captions under `x3naive`
    and `x4ahead`. Not taken, deliberately: `.platform` (the service returns
    a zeroed `logicalId`) and `definition.pbir` (the service's `byConnection`
    to the published model would replace the `byPath` Desktop needs to open
    the folder). Files the service does not carry — `diagramLayout.json`,
    `.pbi/` — were left as they were.
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
