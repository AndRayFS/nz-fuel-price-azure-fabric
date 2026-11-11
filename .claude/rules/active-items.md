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

- [ ] **After the 12 Nov 2026 load, before its artifact expires on ~12 Dec** —
  read the `yahoo-probe` artifact of that weekly run: is Wednesday's daily bar
  of the front contract at the run already the settlement (the same day in a
  later snapshot)? If yes, moving the load later is off. If not, a few manual
  probe runs in one evening find when Yahoo writes the settlement, and the
  move is decided from that. `docs/research.md`, 9 Nov 2026.
  - **Status 10 Nov 2026, by hand, Monday 9 Nov's session.** At 23:05 UTC
    (1 h after the close) the daily bar held the last trade, 92.17, against
    about 92.55 at the settlement window. At 01:00 UTC it held the next
    session's first trades and no close; Monday's own bar was gone from the
    answer. Yahoo's day is New York's, and the session that opens at 18:00 ET
    is written into it. So a load moved into 23:00–05:00 UTC would read a
    broken Wednesday. Still open: is the bar back after New York midnight, and
    with the settlement? From 10 Nov `trigger-probe-yahoo` runs the probe at
    17:30 and 01:30 ET, which answers that without manual runs.

- [ ] **12–19 Nov 2026 — a dense probe grid for three sessions, then back to
  2–3 slots.** Owner's decision, 11 Nov 2026: look around broadly before
  narrowing, since something not yet considered may surface — but not near the
  12 Nov load.
  - **Why.** Monday 9 Nov's session was seen four times: 23:05 and 01:00 UTC
    by hand, then the Logic App's first two runs — the first unscheduled,
    fired when it was created. `BZF27.NYM`'s daily bar:
    last trade 92.17 at 18:05 ET; no close and the new session's volume at
    20:00 ET; the settlement, 92.57, at 20:59 ET. `BZ=F` had it only by 01:30
    ET — which answers the item above, for one session. The last settled day
    carried the day before's volume until the next settlement: a delay, not
    the copy `docs/research.md` (9 Nov) and the roll item below describe.
    Four 15-minute bars of 9 Nov were revised by 1–3 c overnight, and a bar
    closed 12 s earlier changed later. Each seen once; none is a rule yet.
  - **Not before the load.** Keep `hours: [1, 17]` until the load of Thursday
    12 Nov, 09:07 NZDT, has finished. The grid makes 192 Yahoo requests a day
    instead of 16, Yahoo's limits are not measured, and the nowcast reads the
    same endpoint — a failed request drops the week to plain `adl_ecm`.
  - **Then, the same morning.** First the load's own probe snapshot (the item
    above). Then `infra/logic-apps/trigger-probe-yahoo.json` to every hour
    0–23 at `minutes: [30]`, Monday to Saturday, redeployed by
    `docs/ci_setup.md` 7b: the owner pastes the probe's token with `read -rs`,
    Claude cannot. Check `nextExecutionTime` after (7e). Deployed by 10:30 NZDT
    it sees Wednesday's close from both sides (16:30, 17:30 ET); 13:30 NZDT
    (19:30 ET) is the last moment that still covers Wednesday's write window,
    20:00–21:00 ET (14:00–15:00 NZDT).
  - **Status 12 Nov 2026, 10:12 NZDT: deployed.** The load finished at 09:18
    (run 43093459017; GitHub showed it `in_progress` until 10:00, a status
    write, not the chain). Redeployed 21:12:37 UTC, `nextExecutionTime`
    21:30 UTC (16:30 ET Wednesday). The load's own snapshot, 20:07 UTC, is that
    run's `yahoo-probe` artifact; its settlement question needs a later one.
  - **Runs through** Wednesday evening and the Thursday and Friday sessions, to
    01:30 ET Saturday 14 Nov (19:30 NZDT).
  - **Back to 2–3 slots before the 19 Nov load** (09:07 NZDT Thursday): read
    the snapshots, pick the hours by the hypotheses left, redeploy (a second
    token paste). For a moved load the one that matters is whether the
    settlement is in the bar *by symbol* at the candidate time on every
    session; `BZ=F`'s timing does not, the nowcast reads Wednesday by symbol
    (`pipeline/nowcast.py`, docstring).
  - **The probe's token expires ~8 Feb 2027** — 90 days from 10 Nov, per
    `cb46862`; `docs/ci_setup.md` 7a's "No expiration" is the weekly load's.
    That is before the BST item above: reissue it if the probe is still
    needed then.

- [ ] **The `BZF27` → `BZG27` roll, ~20 Nov – 1 Dec 2026** — second observation
  of "Yahoo's live view follows the most traded contract" (one roll so far:
  volumes crossed on 22 Oct, the view switched on 23 Oct; `docs/research.md`,
  10 Nov 2026). From the probe's artifacts, which are kept 30 days: the first
  day `BZG27`'s daily volume exceeds `BZF27`'s, against the first day hourly
  `BZ=F` is on February. Discount a volume equal to the day before; on 6 Nov
  Yahoo copied it. GitHub's cron never fired (9 Nov 2026). From 10 Nov the
  probe is dispatched by `trigger-probe-yahoo`, twice a day, Monday to
  Saturday.

- [ ] **At the 19 Nov 2026 load: the first Gaspy reading against MBIE.**
  Gaspy is the one external, same-week view of the pump price: it shows the
  direction before MBIE does, even where its level differs. On Thursday
  12 Nov the owner read Gaspy's national average 91 at **$3.368**, once, by
  hand.
  - **Compare with `board_price`** for the week stamped 13 Nov (Monday 9 to
    Sunday 15 Nov; 12 Nov is its middle). Gaspy shows pylon prices;
    `adjusted_retail_price`, which the model forecasts, sits 3.75 c/L lower for
    91 in every week since September.
  - **The call for that week**, archive 2026-11-12: `pred_nowcast` 333.4,
    i.e. 337.1 in board terms. Against MBIE's board for 6 Nov (351.9), Gaspy
    reads −15 c/L; the call was −14.7.
  - **One point gives one week's offset**, not a rule. The Gaspy–MBIE offset
    has never been measured, and a few cents either way would be unremarkable.
    A second Gaspy reading on any later day gives a change, which the offset
    cancels out of — the trend without the level.
  - **On close:** the offset goes into `docs/research.md`, "Sources checked
    for a timely series", under Gaspy. If Datamine answers first (the item
    below), its daily series supersedes this.

- [ ] **Datamine: waiting on Andy Marsden, emailed 11 Nov 2026** — the daily
  retail series for the nowcast (`docs/research.md`, "Sources checked for a
  timely series"): national 91, 95 and diesel, history from 2022. Gaspy's
  referral (6 Nov) led through three Datamine auto-replies — Janneke Krieg,
  Sophie Wiltshire, Rosie Nash, all gone — to `andy.marsden@datamine.com`, a
  Partner. The other three auto-replied within minutes; he had not by the
  time of writing, so the mailbox is live.
  - **The product, from `datamine.com/data/fuel-price-nz`:** daily, 1,500+
    stations, history from Nov 2015, API or flat files, sold "for both
    commercial use and research", priced on request. Aimed at companies
    "with meaningful operational or analytical requirements", so a quote is
    the likely answer.
  - **No budget (owner, 11 Nov 2026).** Only free research access, or data
    for credit, is in reach; the odds are low. A paid quote closes this item
    as "not now", not as a negotiation.
  - **If silent by ~18 Nov, in this order:** the enquiry form on that same
    page (detailed; a text fetch does not show it, open it in a browser);
    LinkedIn to Andrew Marsden, then Matt Wilkins (both Partners); the
    Auckland office, 09 303 2300, to ask who owns the fuel data now.
    Commercial Operations / Business Development has no names and is not
    needed unless Marsden passes it on.
  - **fuelwatch.nz — separate, for networking.** An independent project the
    size of this one: Auckland, AdSense-funded, national averages taken from
    `gaspy.nz/stats.html`, no licence, API or history download. Not a data
    source; the owner wants to talk and see whether something can be done
    together (it shows the price now, Report 1 the likely course). Contact
    is its `/contact` form only; no text drafted yet.
  - **On close:** move the product facts and the outcome into
    `docs/research.md`, "Sources checked for a timely series", and add
    fuelwatch.nz there beside fuelclock.nz.
