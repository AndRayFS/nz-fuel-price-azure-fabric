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

- [ ] **The `BZF27` → `BZG27` roll, ~20 Nov – 1 Dec 2026** — second observation
  of "Yahoo's live view follows the most traded contract" (one roll so far:
  volumes crossed on 22 Oct, the view switched on 23 Oct; `docs/research.md`,
  10 Nov 2026). From the probe's artifacts, which are kept 30 days: the first
  day `BZG27`'s daily volume exceeds `BZF27`'s, against the first day hourly
  `BZ=F` is on February. Discount a volume equal to the day before; on 6 Nov
  Yahoo copied it. GitHub's cron never fired (9 Nov 2026). From 10 Nov the
  probe is dispatched by `trigger-probe-yahoo`, twice a day, Monday to
  Saturday.

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
