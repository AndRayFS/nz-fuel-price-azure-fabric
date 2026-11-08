# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.
Open items only: once an item closes, move anything durable to `docs/` and
delete it here.

- [ ] **~mid-Oct 2026, not arrived by 4 Nov** — Stats NZ releases the September-quarter CPI, and
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
  - **Status at the 4 Nov 2026 load:** not arrived. Every week from 3 Jul is
    still Provisional (last Final: 26 Jun), and `monitor_revisions` has no
    Provisional → Final transition since 18 Sep — only the usual one-week
    `provisional_revised` rows. Q2 finalised on 26 Aug, two months after its
    last week; the same gap from 25 Sep puts Q3 around 25 Nov.

- [ ] **`rounded_check` not yet exercised against a precision flip.** The
  snapshot fix of 17 Sep (`docs/mbie_notes.md`, "Known structural changes",
  16 Sep) is proven by arithmetic only. On the next flip, expect
  `final_rewritten` in the single digits rather than the thousands — then
  delete this item. Query: `select detected_on, revision_class, count(*) from
  monitoring.monitor_revisions where detected_on >= '2026-09-18' group by
  detected_on, revision_class`.

- [ ] **Before 28 Mar 2027, when the UK goes onto BST** — decide where the
  nowcast takes Monday's and Tuesday's FX. Under BST a live `NZDUSD=X` daily
  bar lands on Tuesday, and whether it is already the midnight price at the
  run is not measured. Options and why it cannot be seen before March:
  `docs/workstreams.md`, W23, Risks, "The live FX bar".
