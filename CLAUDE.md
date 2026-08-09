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

`docs/architecture.md` — every non-obvious design choice, every bug found
and how, full backtest results, prioritized roadmap. Don't duplicate its
content here; read it.

`docs/mbie_notes.md` — source data gotchas.

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
