# Active / time-sensitive items

Check dates against today before relying on this file — it goes stale by
design and should be trimmed or updated, not left as-is indefinitely.

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
