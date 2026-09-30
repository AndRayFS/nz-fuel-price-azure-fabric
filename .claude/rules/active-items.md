# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

- [x] **The dispatch token does not expire, and that was the choice —
  19 Sep 2026.** The Logic App authenticates to GitHub with a fine-grained PAT
  called `nz-fuel-dispatch`, scoped to this repository alone, permissions
  `Actions: read and write` plus the compulsory `Metadata: read`. It is set to
  **No expiration**, so there is no date on this item and nothing to renew.

  That is deliberate, and it is the opposite of what the plan assumed. An
  expiring token produces exactly the failure W16 exists to remove: the trigger
  quietly stops, and with the backstop cron gone the week simply does not load.
  A credential that cannot die of old age removes that failure entirely, and
  what it costs is bounded — one public repository with no secrets in it, one
  permission, and the worst it buys an attacker is starting and cancelling
  workflow runs, wasting capacity that the watchdog, the `always()` pause and
  the 23:00 NZT auto-pause all close behind them.

  **The standing obligation is therefore not a date but a reflex: if the token
  ever leaks, revoke it on GitHub and redeploy the Logic App with a new one.**
  It lives in exactly one place, as a `securestring` parameter on the workflow
  — in no file, no repository and no conversation.

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

- [x] **The precision flip is a habit, and the snapshot no longer records it —
  17 Sep 2026.** The 16 Sep load cut `Value` to ~10 significant digits again,
  the third flip in three publications, and wrote another 15,848
  `final_rewritten` versions at deltas no larger than 5e-8 c/L. That was the
  condition this item was watching for, so the fix it named is in:
  `snapshots/mbie_revisions.sql` now uses strategy `rounded_check`
  (`macros/snapshot_rounded_check.sql`), which compares `Value` as a number
  rounded to 4 decimals on **both** sides. Nothing stored changed and no
  transition wave was written — verified the same day, zero versions from
  `dbt snapshot` with the rounding in the executed SQL. Measurements and what
  the rounding gives up: `docs/mbie_notes.md`, "Known structural changes",
  16 Sep.
  - **Not yet exercised against a flip.** The proof so far is arithmetic on
    the two precisions already in the table (8 of 16,034 versions survive),
    not a load. The next flip is the real test: after the 24 Sep load, expect
    `final_rewritten` in the single digits rather than the thousands. Delete
    this once that has happened.
    Query: `select detected_on, revision_class, count(*) from
    monitoring.monitor_revisions where detected_on >= '2026-09-18' group by
    detected_on, revision_class`.
  - **The six genuine revisions of 16 Sep** were all in week 2026-09-04:
    `Importer cost` up and `Importer margin` down by the same amount, diesel
    0.397 and both petrols 0.697 c/L. Those survive the rounding; they are the
    kind of thing this table exists to catch.

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
    project is normally driven from. **That is fine: the owner reads that
    mailbox daily** (stated 19 Sep 2026). This note used to say an alert nobody
    reads is not a guard and ask for a second contact; the premise was wrong,
    not the principle. No second contact is needed, and the same mailbox is now
    the destination for the weekly load's own alarm.
  - All four thresholds are **Actual**, not Forecasted, so the first warning
    arrives after NZ$10 is already spent. At NZ$17.50/day for a capacity left
    running, that is about half a day of drift. A forecasted threshold would
    warn earlier; not added, because the auto-pause is meant to make that case
    impossible and adding one would be guarding against the guard.

- [ ] **~27 Sep 2026** — the Power BI Pro trial ends ~26 Sep. The day
  after, open Report 1's public link and check it still renders with data.
  Report 1 is now served via Publish to web from **My Workspace** and costs
  nothing, but it is unresolved whether that survives on a Free licence —
  Microsoft's docs point both ways. If it breaks: Pro (~NZ$24/mo), or back
  to PDF. Details in `docs/architecture.md` (Stack question) and
  `docs/cost_notes.md`.
