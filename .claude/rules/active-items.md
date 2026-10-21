# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.
Open items only: once an item closes, move anything durable to `docs/` and
delete it here.

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

- [ ] **`rounded_check` not yet exercised against a precision flip.** The
  snapshot fix of 17 Sep (`docs/mbie_notes.md`, "Known structural changes",
  16 Sep) is proven by arithmetic only. On the next flip, expect
  `final_rewritten` in the single digits rather than the thousands — then
  delete this item. Query: `select detected_on, revision_class, count(*) from
  monitoring.monitor_revisions where detected_on >= '2026-09-18' group by
  detected_on, revision_class`.
