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
    removed a petrol one; the numbers in `docs/architecture.md` are written
    against 29 Aug 2026 and will need the same treatment again.
  Method and expectations: `docs/mbie_notes.md`, "A standing prediction".

- [x] **28 Aug 2026 — done, run on 27 Aug.** Gate, run and `mark_processed`
  all behaved; the June quarter finalised in the same release (thirteen
  weeks, 3 Apr – 26 Jun). What it changed: `docs/architecture.md`, "The
  quarter finalised". Kept here until the next weekly run has exercised the
  gate chain a second time, then delete. The reasoning for skipping 26 Aug
  is in `docs/workstreams.md`; the chain itself is in `QUICKSTART.md`.

- [ ] **Before the next Power BI refresh** — republish the `nz_fuel_v2`
  semantic model from Desktop. `flag_data_status` was removed from
  `forecast_accuracy` on 27 Aug 2026 (W14) and the `column flag_data_status`
  block was deleted from the `.tmdl` in the repo, but the **deployed** model
  still declares it until someone publishes. The partition pulls the whole
  table, so a model declaring a column the table no longer has fails on
  refresh. The report was refreshed for week 2026-08-21 *before* the removal,
  so nothing is broken today — the trap is the next weekly run, which would
  refresh a stale model against a narrower table. Publish first, refresh
  second.

- [ ] **27 Aug 2026** — the Azure free-trial credit expires. NZ$274.98 was
  left on 14 Aug, against ~NZ$2.40/day of actual burn, so ~NZ$245 will
  simply lapse. Credit does **not** carry past this date, and upgrading to
  pay-as-you-go early does not extend it — the 30-day window is fixed from
  sign-up (~28 Jul). Two consequences:
  - Until 27 Aug, F2 compute is effectively free. Anything heavy worth
    doing — full-history `--full-refresh` runs, lag experiments, gold
    rebuilds — is cheapest now.
  - From 28 Aug, F2 bills real money (NZ$0.729/hour, i.e. NZ$17.50/day if
    it ever runs 24 h). Fabric is not in the 12-months-free list, so nothing
    shields it. Upgrading also **removes the spending limit**, which is
    today's backstop — after that the only guards are the 23:00 NZT
    auto-pause and whatever budget alert exists.

- [ ] **~27 Sep 2026** — the Power BI Pro trial ends ~26 Sep. The day
  after, open Report 1's public link and check it still renders with data.
  Report 1 is now served via Publish to web from **My Workspace** and costs
  nothing, but it is unresolved whether that survives on a Free licence —
  Microsoft's docs point both ways. If it breaks: Pro (~NZ$24/mo), or back
  to PDF. Details in `docs/architecture.md` (Stack question) and
  `docs/cost_notes.md`.
