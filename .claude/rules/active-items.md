# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

- [ ] **28 Aug 2026** — run the weekly update that was deliberately skipped
  on **Wed 26 Aug**. The owner is away 25–27 Aug with no laptop, and MBIE
  publishes on the Wednesday in the middle of that. Skipping costs two days
  of staleness on a report that already labels itself a retrospective
  simulation; rushing unattended automation into place before a trip costs
  more. This is also the first run that bills real money — a few cents.
  Reasoning and the full plan: `docs/workstreams.md`.

  It is also the **first run through the freshness gate** (W3, landed
  22 Aug). Start with `python pipeline/gate.py` and read its exit code —
  `0` go, `2` nothing to do, `1` stop and look — and finish with
  `python pipeline/mark_processed.py`, which the gate depends on for next
  week. `QUICKSTART.md` has the full chain.

- [ ] **23 Aug 2026** — retire the old Report 1 from My Workspace. The
  redesign (`docs/report1_redesign.md`) is published alongside it as a
  separate artifact, deliberately, so the two run in parallel for about a
  week.

  **`nz_fuel_v2` — the redesign — was published to My Workspace on 17 Aug
  2026 and is served at**
  `app.powerbi.com/view?r=eyJrIjoiZGQ4YzE2OWUtNTg1Zi00NzY4LWFiYTUtNGJmYTJlZmNkOWFiIiwidCI6IjY2YWVkMTI5LWFjZWQtNDgyOS05NzAxLTZiNzMxNTY3NWEwNCJ9`.
  The old `nz_fuel` report keeps its own separate link until 23 Aug.

  On 23 Aug: delete the old `nz_fuel` report **and** its semantic model, then
  confirm `/admin/widelySharedArtifacts/publishedToWeb` is back to a single
  entry. Until then two publish-to-web links and two import models exist,
  and each weekly update has to refresh both. Names must stay distinct the
  whole time — two artifacts called `nz_fuel` is the failure documented in
  `docs/architecture.md`. Export a pbix backup before deleting, outside the
  repo, as was done on 13 Aug.

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
