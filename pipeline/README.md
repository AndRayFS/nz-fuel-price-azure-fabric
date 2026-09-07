# `pipeline/` — the weekly deterministic recompute

Code that runs every week on settled algorithms with no human in the loop.
Nothing here is exploratory; nothing here should need a judgement call at
runtime. `research/` is the other half — estimation loops, twenty
specifications, work that is meant to be read and argued with. The split is
W5 in `docs/workstreams.md`, landed 7 Sep 2026: `export_panel.py`,
`build_period_flags.py` and `backtest.py` moved here from `research/`, and
the derived data they read and write moved with them, to `data/` at the
repository root — owned by neither package, gitignored, rebuilt by steps 5–7
of the weekly chain.

| file | what it does |
|---|---|
| `gate.py` | the freshness gate — the only step allowed to stop the weekly run |
| `export_panel.py` | the weekly panel out of the warehouse into `data/panel_weekly.csv` |
| `build_period_flags.py` | the regime axes, derived from the panel by rule, into `seeds/period_flags.csv` |
| `backtest.py` | refits every method at every cutoff; writes `seeds/forecast_history.csv` and `data/backtest_results.csv` |
| `mark_processed.py` | closes the run by recording which week was processed |
| `fabric_io.py` | the warehouse connection and the Fabric REST calls both need |
| `test_gate.py` | replays the gate's decision against the runs that happened |
| `vintage.py` | puts the whole system on a past date, and brings it back |

`aip_check.py` stayed in `research/`. It runs weekly, but it parses a PDF
whose layout is the source's to change, and a step that needs a person the
week AIP restyles page 3 is not the same kind of code as the five above.
The weekly chain therefore still calls one script out of `research/`.

**Order inside the chain is not cosmetic.** `build_period_flags.py` reads
the panel and `backtest.py` reads the flags; the centred nine-week window
moves the last four weeks' regime values every time a week lands, so running
the flags after the backtest leaves the split on last week's regimes.

`vintage.py` is the one file here that does **not** run weekly. It lives in
this package rather than `research/` because it is deterministic, needs no
judgement at runtime, shares `fabric_io`, and — decisively — the gate depends
on the marker it writes. An exploratory script cannot be a precondition of the
weekly run.

## The gate

Runs first, after the ingest and before anything else. Three exit codes:

| code | meaning | what should happen next |
|---|---|---|
| 0 | new data, and it landed | run the rest of the chain |
| 2 | nothing to do — no new week | do not run the chain; nobody need look |
| 1 | stop and look | do not run the chain; go and read why |

**The verdict binds, since W7 (7 Sep 2026).** The chain is declared in
`Taskfile.yml`, where every step comes after `gate`, so a non-zero code stops
the run rather than merely advising against it. Before that the chain was a
markdown block a person pasted, and pasting it whole on a `nothing_new` week
ran every step after the gate on unchanged data.

```bash
task weekly                        # the gate first, then the rest
python pipeline/gate.py; echo "gate said $?"    # just the verdict
```

Exit 2 is not an error and must not be reported as one. What separates it from
1 is only whether anyone needs to investigate, not whether the chain runs —
neither code lets the chain run. `task` prints a failure line either way, so
the `gate` task prints its own explanation first: on a 2 it says in words that
stopping was the intended outcome.

`gate.py`'s module docstring carries the reasoning — in particular why it
reads what arrived rather than what MBIE published, which is not what W3
originally specified.

## Vintages

```bash
python pipeline/vintage.py --as-of 2026-08-13   # go there
python pipeline/vintage.py --status             # what is loaded right now
python pipeline/vintage.py --return             # come home
```

Do not set `as_of_vintage` by hand. It moves six warehouse objects out of
eighteen and leaves `forecast_accuracy` — the table Report 1 leads with — on
today's data, with nothing recording the discrepancy. The script runs the whole
six-step chain, restores the hand-written seeds from the commit current on that
date, and writes the marker the gate reads.

Horizon is 17 July 2026 for data and 1 August 2026 for code, so full system
vintages start at 6 August. A date means the state as that day *ended*.
`QUICKSTART.md` carries the rest.

## Running it

```bash
python pipeline/gate.py            # after the ingest, before everything else
python pipeline/mark_processed.py  # after forecast_accuracy is rebuilt
python pipeline/test_gate.py       # no capacity, no network, no dependencies
```

`gate.py`, `mark_processed.py` and `vintage.py` need the Fabric capacity up and
an `az login`. `test_gate.py` needs neither.

## State

`pipeline.processed_weeks` in the warehouse — its own schema, alongside
`monitoring`, because it is neither a source, a model, nor a signal. One
append-only row per completed run:

```
processed_week | bronze_rows | ingest_run_id | ingest_rows_read | recorded_at
```

The table is created on first write, so a fresh warehouse needs no setup step.

`pipeline.warehouse_vintage` in the same schema — what date the warehouse is
standing on. Append-only, newest row wins, `as_of` null meaning current:

```
as_of | code_commit | silver_weeks | entered_at
```

It exists because a vintage warehouse is otherwise undetectable — bronze does
not move when silver goes back, so every freshness check passes on a warehouse
that must not be run against. The gate reads it *first*, before anything about
freshness.
