# Part 13 draft — the overview (notes, not yet a post)

Status: **collecting, opened 15 Oct 2026.** Nothing below is chosen. Each item
is a candidate with a pointer to where its evidence lives; the owner picks
what goes in and writes the text.

**Place in the series.** Part 12 is the automation post, promised by Part 9
and again by Part 11. This one is the overview that closes the active phase:
what was built, what held, what did not, and what the project cannot see.

**Timing.** After MBIE finalises Jul–Sep 2026 (expected mid-Oct, see
`.claude/rules/active-items.md`) and `research/headline_results.py` has been
re-run on it. The research numbers are written against 29 Aug 2026, and the
last finalisation reversed a diesel result and removed a petrol one. Any
figure that makes it into the post is re-measured on the day it is quoted,
per `.claude/rules/working-style.md`.

## What it is, in one paragraph

The R lag analysis from Part 1, rebuilt on a Fabric warehouse, dbt and
Power BI; a weekly load that runs with nobody at the keyboard; Report 1 on a
public link.

## What held

- **The model beats "the price won't move".** Walk-forward, every method
  refit on data up to each week only: ADL+ECM 20–27% lower MAE than naive,
  both fuels, all three horizons, outside crisis weeks (15 Aug 2026).
  `docs/research.md`, "Walk-forward test".
- **The published rule did not.** The formula Report 1 originally used lost
  to doing nothing. A negative result that earned its place (Part 7).
- **Independent agreement with MBIE.** The project's lowest margins and its
  one-to-two-week lag matched MBIE's own restart analysis exactly — at the
  time. MBIE's 23 Sep revision has since moved the margins.
  `docs/mbie_notes.md`, "MBIE's own findings".
- **What actually drove the crisis.** Landed cost, not crude and not margin
  (Part 8). `docs/research.md`, "What actually drove pump prices through the
  2026 crisis".
- **The pipeline caught the source's own problems.** A CDN that served last
  week's file while every test passed (19 Aug); a precision flip that read as
  15,848 revisions (16 Sep); a methodology change that rewrote seven months
  of margins (23 Sep). A source that revises itself turned out to be the
  normal case, not the exception.
- **Report 1 costs nothing to serve.** Publish-to-web from My Workspace, and
  it survived the end of the Power BI Pro trial (checked 8 Oct).

## What did not

- **Rockets and feathers.** Four attempts, not found.
  `docs/research.md`, "Rockets and feathers, fourth attempt".
- **Asymmetry.** Three versions of the finding; none survived.
- **Lag stability as a crisis signal.** Withdrawn 15 Aug.
- **Diesel's "lag shift".** A flat peak, not a regime change (13 Aug).
- **A better slope made the forecast worse** (8 Sep).
- **The always-on claim of Parts 5–6.** Wrong for Power BI, corrected in the
  comments the same day.

## What the project cannot see

- **Paid data.** Argus and Platts product prices, and the physical premium
  over them, are behind a paywall. Since MBIE's 23 Sep change its importer
  cost includes a "fuel market adjustment" built from that paid data, and
  after 11 Sep it cannot be separated from the market move. The AIP
  comparison existed only because the real benchmark is paid.
- **n = 1.** Every crisis claim rests on one episode. For margin
  compression, comparable data starts on 29 Mar 2024 and holds exactly one
  episode per fuel. `docs/research.md`, "n = 1".
- **A simulation, not a record.** The report shows what the model *would
  have* said at each past week — refit on what was known then, but in
  today's revised version of the data. What it actually said on a given day
  is not kept. It can be reconstructed with the vintage machinery
  (`pipeline/vintage.py --as-of`), with today's code. **Verify before
  claiming that:** the machinery was last exercised on 23 Aug, before the
  backtest moved into the warehouse.
- **The margin is a residual.** MBIE derives the importer margin from a
  replacement cost — this week's spot price at this week's exchange rate —
  so a cost spike compresses it mechanically, whatever was actually paid for
  the fuel already in the tanks.
- **The data moves under the findings.** Quarterly finalisation reversed one
  diesel result and removed one petrol result (29 Aug); the 23 Sep
  adjustment rewrote March–September margins. Posts stay as published;
  corrections are listed in `docs/linkedin_series.md`.
- **The nowcast's Brent is futures**, the wrong price in this market
  (`docs/research.md`, 19 Sep).
- **National weekly averages.** No station-level or regional prices.

## What keeps running

- The weekly load, Thursday 09:07 NZT, with an alarm to the owner's mailbox
  when it does not succeed.
- Still needs a human: a republish from Power BI Desktop when the model's
  shape changes, and revoking the dispatch token if it ever leaks. The Power
  BI refresh itself is on this list until the refresh question is settled.
