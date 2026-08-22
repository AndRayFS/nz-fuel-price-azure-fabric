# `pipeline/` — the weekly deterministic recompute

Code that runs every week on settled algorithms with no human in the loop.
Nothing here is exploratory; nothing here should need a judgement call at
runtime. `research/` is the other half — estimation loops, twenty
specifications, work that is meant to be read and argued with. The split is
W5 in `docs/workstreams.md`, and it is only half done: `export_panel.py`,
`build_period_flags.py` and `backtest.py` are production code still sitting
in `research/`. They move in that branch.

| file | what it does |
|---|---|
| `gate.py` | the freshness gate — the only step allowed to stop the weekly run |
| `mark_processed.py` | closes the run by recording which week was processed |
| `fabric_io.py` | the warehouse connection and the Fabric REST calls both need |
| `test_gate.py` | replays the gate's decision against the runs that happened |

## The gate

Runs first, after the ingest and before anything else. Three exit codes:

| code | meaning | what the chain does |
|---|---|---|
| 0 | new data, and it landed | carry on |
| 2 | nothing to do — no new week | stop, quietly |
| 1 | stop and look | stop, loudly |

Exit 2 is not an error and must not be treated as one. Under `set -e` the
chain stops on both 1 and 2, which is correct; what differs is whether anyone
needs to go and look.

`gate.py`'s module docstring carries the reasoning — in particular why it
reads what arrived rather than what MBIE published, which is not what W3
originally specified.

## Running it

```bash
python pipeline/gate.py            # after the ingest, before everything else
python pipeline/mark_processed.py  # after forecast_accuracy is rebuilt
python pipeline/test_gate.py       # no capacity, no network, no dependencies
```

Both `gate.py` and `mark_processed.py` need the Fabric capacity up and an
`az login`. `test_gate.py` needs neither.

## State

`pipeline.processed_weeks` in the warehouse — its own schema, alongside
`monitoring`, because it is neither a source, a model, nor a signal. One
append-only row per completed run:

```
processed_week | bronze_rows | ingest_run_id | ingest_rows_read | recorded_at
```

The table is created on first write, so a fresh warehouse needs no setup step.
