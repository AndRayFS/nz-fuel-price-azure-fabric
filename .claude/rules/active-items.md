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

- [ ] **Set a budget alert in Cost Management — nothing guards spend right
  now.** The subscription was upgraded to pay-as-you-go on 3 Sep 2026, which
  **removed the spending limit**. That limit was the backstop, and it is gone;
  what remains is the 23:00 NZT auto-pause and manual discipline. F2 is
  NZ$0.729/hour while resumed (measured — `docs/cost_notes.md`), so a weekly
  run costs about NZ$1 and a capacity left running costs NZ$17.50/day.
  Suggested: NZ$20/month with alerts at 50/80/100%.

- [ ] **Publish `nz_fuel_v2` from Desktop at the next opportunity — four
  columns left `forecast_accuracy` on 7 Sep 2026.** `report1_ish` was
  withdrawn from the backtest (`docs/research.md`), so `pred_report1_ish`,
  `abs_err_report1`, `mae_report1_26w` and `skill_report1_26w` are gone. The
  `.tmdl` in `pbip/` is already updated; the deployed model still declares
  them. No visual or measure read any of the four. Whether a refresh of the
  stale model would actually fail is **untested** — the same situation arose
  with `flag_data_status` on 27 Aug and the model was republished before any
  refresh could settle it. Publishing is cheaper than finding out.
- [ ] **`forecast_accuracy.sql` has not been compiled against the
  warehouse** — `dbt parse` passes, `dbt compile` needs live capacity and was
  refused on 7 Sep. The edit removed three expressions and one CTE column;
  the next weekly run is the first real check.

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
