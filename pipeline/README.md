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

| code | meaning | what should happen next |
|---|---|---|
| 0 | new data, and it landed | run the rest of the chain |
| 2 | nothing to do — no new week | do not run the chain; nobody need look |
| 1 | stop and look | do not run the chain; go and read why |

**Nothing enforces this yet.** The weekly chain is a list of commands in
`QUICKSTART.md` that a person runs; there is no runner, no `set -e`, and no
dependency between the steps. The gate therefore *informs* — it prints its
verdict to stderr and returns a code — and a human decides. Paste the whole
block on a `nothing_new` week and every step after it will run happily on
unchanged data.

Making the code binding is W7, which declares the chain in `Taskfile.yml` so
the steps genuinely depend on the gate. Until then, read the exit code:

```bash
python pipeline/gate.py; echo "gate said $?"
```

Exit 2 is not an error and must not be reported as one. What separates it from
1 is only whether anyone needs to investigate, not whether the chain runs —
neither code lets the chain run.

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
