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

- [ ] **22 Oct 2026 — the first load that refreshes Report 1 by itself.**
  `task refresh` was proven on 15 Oct from this laptop, started by the user.
  In CI the service principal starts `refresh_report_1`, and whether the
  pipeline's connection `pbi-api-andrei` (OAuth, the user's token) holds in
  that case has not been observed; the ingest's connection is in the same
  position and has always worked. Check that run's log for `Report 1's model
  refreshed`, and the model's refresh history for a `ViaEnhancedApi` row at
  about 09:10 NZDT. If it failed on the connection, the week is still loaded
  and closed: fix the access and run `task refresh` alone. Delete this item
  once it has passed.
  - **The same run is the first for two more things (W19):** `task build`
    and `task report` now build `margin_compression`, and `task publish`
    uploads as `nz-fuel-ci` for the first time — proven on 16 Oct from the
    laptop only. Expect a new `2026-10-22/nz-fuel-2026-10-22.zip` in
    `nzfueldata/data` and `latest` carrying the same bytes. A failed upload
    leaves the week loaded and refreshed: `task publish` alone repairs it.
  - **And the first to show the week on the public link by itself.** Expect
    it about as soon as the run ends, around 09:20 NZDT: a refresh clears
    publish-to-web's hour-long cache (`architecture.md`, "Refreshing Report 1
    from the chain"). In the margin table on "The Data", the newest week's
    "Backfilled" should read False, not blank.
  - **Standing, once that has passed: the connection's token can lapse**, and
    its lifetime is not documented anywhere this project has looked. The
    symptom is a red run failing in `task refresh` with the week already
    loaded. Fix: Fabric → Settings → Manage connections and gateways →
    `pbi-api-andrei` → Edit credentials → sign in, then `task refresh`.
    `docs/architecture.md`, "Refreshing Report 1 from the chain".

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

- [x] **AIP markup above the range `architecture.md` records — explained
  8 Oct 2026: it is MBIE's fuel market adjustment, not the market.** The
  hand cross-check of 10 Sep (diesel 14.42 → 14.57, petrol 10.40 → 10.23
  USD/bbl, weeks 28 Aug → 4 Sep) was made before the 16 Sep revision and the
  23 Sep adjustment; `monitor_aip_gap`, read 8 Oct, has the same weeks at
  16.62 → 17.53 and 12.32 → 14.59. In `Importer cost` terms the difference is
  diesel 2.3 and 3.2, petrol 2.0 and 4.7 c/L — 2.8 and 4.0 for 4 Sep net of the
  16 Sep revision — inside the adjustment's measured Jul–Sep size of −0.04 to
  +7.1 (diesel) and +0.7 to +9.0 (petrol): `docs/mbie_notes.md`, "Known
  structural changes", 23 Sep. Two things follow.
  - **The ranges in `architecture.md` stay as they are.** 6.9–13.4 and
    7.4–9.6 were measured under the old methodology. From 27 Feb 2026
    MBIE − Argus is the old markup plus the adjustment, and a new range would
    be a range of that sum.
  - **After 11 Sep the adjustment cannot be separated.** MBIE publishes only
    the sum, the snapshot holds unadjusted values only up to 11 Sep, and the
    product differential is paid Argus data. The climb to ~24 USD/bbl on both
    fuels by 2 Oct is probably the adjustment and cannot be shown to be. That
    is W18's third argument; the unflagged diesel week of 2 Oct (ours +1.01
    against Argus −2.02 USD/bbl) is an instance of it.

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
