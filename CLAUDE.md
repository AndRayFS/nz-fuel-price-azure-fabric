# NZ Fuel Price Project

Rebuilding an R-based NZ fuel-price lag analysis (oil price shocks → pump
prices) on Azure/Microsoft Fabric + dbt + Power BI. GCP background; this
project exists to get hands-on with the Microsoft stack specifically —
see "Stack question" in `docs/architecture.md` before suggesting a switch.

## Stack

dbt-core + `dbt-fabric-samdebruyn` (community adapter, not the official
Microsoft one) · Fabric Warehouse (T-SQL) · Power BI Desktop. Python venv,
not Docker.

## Start of every session

```bash
source .venv/bin/activate
dbt --version   # confirm venv + fabric adapter registered
```

Full command reference: `QUICKSTART.md`. **Always `--full-refresh` for
weekly data updates** — plain `dbt run` has silently missed new bronze
rows for the gold models before.

## Read before changing `models/gold/`

Split in two on 3 Sep 2026, along the line of *consumption* rather than
language or directory:

`docs/architecture.md` — the contour that runs weekly with no human in it:
ingest, bronze through silver, the freshness gate, monitoring, the semantic
model, and the vintage machinery. `export_panel.py`, `build_period_flags.py`
and `backtest.py` are production — they live in `pipeline/` since W5 — and are
documented there.

`docs/research.md` — methods and measurements: the distributed-lag work,
pass-through, the walk-forward test, and the corrections that overturned
earlier findings. Withdrawn findings are kept in its appendix.

**Half of `models/gold/` is read by nothing.** `lag_correlation`,
`lag_resolved`, `factor_volatility` and `volatility_config` are still built
by every weekly `--full-refresh`, but `nz_fuel_v2` holds only
`forecast_accuracy`, which descends from two seeds. Before changing any of
those four, read "The T-SQL lag layer" at the end of `architecture.md` —
the decision to keep, unschedule or delete them is open.

Don't duplicate either file's content here; read them.

`docs/mbie_notes.md` — source data gotchas.

`docs/workstreams.md` — the current plan of record: twelve pieces of work,
one branch each, with dependencies and a conflict map. Read it before
starting anything structural.

## Critical rules

- Verify empirically before asserting — don't assume a dbt-fabric or
  Power BI DAX behavior "should" work.
- After writing multi-line SQL/config via heredoc, `grep`/`cat` to confirm
  it landed before running — heredocs have silently truncated content
  before.
- One change at a time, verify, then the next.
- No point-forecast language ("predict," "will be") on `Report1` measures
  — see architecture.md's confidence-tier framing.

More detail: `.claude/rules/working-style.md` (working conventions, tooling
split with claude.ai chat) and `.claude/rules/active-items.md`
(time-sensitive, check-the-date items).

## Reviewing a weekly load

`/load-review` (`.claude/skills/load-review/`) fixes the *shape* of that
answer — what arrived, whether anything in it is an outlier, how far it
diverged from the forecast — and deliberately leaves the source of the
numbers open. It also records which predictors belong in such a review:
only the two Report 1 actually plots, `pred_adl_ecm` and `pred_naive`.
