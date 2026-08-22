"""Put the whole system on a past date, and bring it back.

WHY A SCRIPT AND NOT TWO COMMANDS. `as_of_vintage` moves silver, and gold
follows it through `ref()`. That is six objects out of eighteen. The rest of
the warehouse does not move: three derived seeds, three hand-written ones, and
`forecast_accuracy`, which descends from seeds only and never reads silver.
Running the var alone therefore leaves the warehouse in a state where the lags
stand on one date and `skill_26w` — the number Report 1 leads with — stands on
another, with nothing anywhere saying so. That is not a vintage; it is a
mixture. This script is the whole operation, so that entering and returning
cannot come apart.

WHAT "THE SYSTEM ON A DATE" MEANS HERE. Two dimensions, treated differently
and deliberately:

  * DATA moves. MBIE numbers come from the snapshot filtered by validity, and
    the hand-written seeds (`periods`, `variable_mapping`, `brent_daily`) are
    restored from the commit that was current on that date. Both are versioned;
    both are honoured.

  * CODE does not. Models, macros and tests stay as they are today. This is a
    choice, not an oversight. The question worth asking is "what would today's
    method have said on the data available then", which is the question that
    has no look-ahead in it. Running the old code instead answers "what did the
    report say that day", which is archaeology, and it would reproduce bugs
    this project has since found and documented rather than test anything. Old
    code is still reachable through git if that is ever wanted — but note it
    could not read a vintage without backporting `weekly_prices_relation`,
    so it would not be purely historical either.

HORIZON. 17 July 2026, the snapshot backfill date. Earlier dates hold exactly
one version and would silently return current numbers, so they are refused
rather than served.

THE MARKER. `pipeline.warehouse_vintage` records every transition, append-only,
newest row wins. It exists because a vintage warehouse is otherwise
undetectable: the freshness gate compares bronze against
`pipeline.processed_weeks`, and neither moves when silver goes back. Anything
that cares — the gate, a human, a future report footer — can ask this table
what it is looking at.

Usage:
    python pipeline/vintage.py --as-of 2026-08-13    # go there
    python pipeline/vintage.py --return              # come home
    python pipeline/vintage.py --status              # what is loaded now
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import fabric_io

REPO = Path(__file__).resolve().parents[1]

# The snapshot's first version. Before this every row has one version, so a
# vintage would quietly be the current data wearing a date.
HORIZON = date(2026, 7, 17)

# Versioned by a person, not accumulated: restored from git at the target date
# rather than recomputed. The derived seeds are absent on purpose — they are
# rebuilt from vintage silver further down.
HAND_WRITTEN_SEEDS = [
    "seeds/periods.csv",
    "seeds/variable_mapping.csv",
    "seeds/brent_daily.csv",
]

SCHEMA = "pipeline"
TABLE = "warehouse_vintage"

DDL = f"""
create table {SCHEMA}.{TABLE} (
    as_of        date             null,
    code_commit  varchar(40)  not null,
    silver_weeks int          not null,
    entered_at   datetime2(3) not null
)
"""


def sh(*args: str, cwd: Path = REPO) -> str:
    """Run a command, echo it, fail loudly."""
    print(f"  $ {' '.join(args)}", flush=True)
    out = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if out.returncode != 0:
        sys.stderr.write(out.stdout + out.stderr)
        raise SystemExit(f"failed: {' '.join(args)}")
    return out.stdout


def dbt(*args: str, as_of: str | None) -> None:
    extra = [] if as_of is None else ["--vars", json.dumps({"as_of_vintage": as_of})]
    sh("dbt", *args, *extra)


def commit_as_of(as_of: str) -> str:
    """The commit that was HEAD at the end of that day, on the current branch."""
    out = sh("git", "rev-list", "-1", f"--before={as_of} 23:59:59", "HEAD").strip()
    if not out:
        raise SystemExit(
            f"no commit on this branch at {as_of} — the repository starts later"
        )
    return out


def working_tree_is_clean() -> bool:
    return sh("git", "status", "--porcelain", "--", "seeds", "research/data").strip() == ""


def existed_at(commit: str, path: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}:{path}"],
        cwd=REPO, capture_output=True,
    ).returncode == 0


def restore_seeds(commit: str) -> tuple[list[str], list[str]]:
    """Put the hand-written seeds back to `commit`.

    Returns (moved, absent). A seed that did not exist yet at the target date
    is left at HEAD rather than deleted: `brent_daily` arrived on 15 Aug 2026,
    and removing it would break `export_panel.py`, which joins it. The vintage
    is then imperfect in one stated way instead of failing outright — and the
    caller prints which way, because an unstated approximation is worse than
    either.
    """
    present = [f for f in HAND_WRITTEN_SEEDS if existed_at(commit, f)]
    absent = [f for f in HAND_WRITTEN_SEEDS if f not in present]
    if not present:
        return [], absent
    before = {f: sh("git", "hash-object", f).strip() for f in present}
    sh("git", "checkout", commit, "--", *present)
    moved = [f for f in present if sh("git", "hash-object", f).strip() != before[f]]
    return moved, absent


def chain(as_of: str | None) -> None:
    """The six steps, in the only order that leaves nothing behind.

    Steps 1-2 stand silver and gold up on the target data. Steps 3-5 rebuild
    the derived seeds from that silver — `period_flags` is in there because it
    is derived from the panel by rule and `backtest.py` reads it alongside the
    panel, so skipping it would leave the regime axes on today's data while the
    prices went back. Step 6 seeds them and step 7 rebuilds `forecast_accuracy`
    on top, which is the only way that table ever moves.

    The `forecast_accuracy` built at step 2 is transient and wrong by one
    generation. It is cheaper to overwrite it at step 7 than to teach this
    script which models to skip.
    """
    py = sys.executable
    dbt("seed", "--full-refresh", as_of=None)
    dbt("run", "--full-refresh", as_of=as_of)
    sh(py, "research/export_panel.py")
    sh(py, "research/build_period_flags.py")
    sh(py, "research/backtest.py")
    dbt("seed", "--select", "period_flags", "forecast_history", as_of=None)
    dbt("run", "--full-refresh", as_of=as_of)


def ensure_table(cur) -> None:
    cur.execute(
        "select count(*) from INFORMATION_SCHEMA.SCHEMATA where schema_name = ?",
        [SCHEMA],
    )
    if cur.fetchone()[0] == 0:
        cur.execute(f"create schema {SCHEMA}")
    cur.execute(
        "select count(*) from INFORMATION_SCHEMA.TABLES "
        "where table_schema = ? and table_name = ?",
        [SCHEMA, TABLE],
    )
    if cur.fetchone()[0] == 0:
        cur.execute(DDL)


def mark(as_of: str | None) -> int:
    """Record what the warehouse now holds, and report silver's newest week."""
    commit = sh("git", "rev-parse", "HEAD").strip()
    with fabric_io.connect() as conn:
        cur = conn.cursor()
        ensure_table(cur)
        cur.execute("select count(*) from dbo.silver_general")
        weeks = cur.fetchone()[0]
        cur.execute(
            f"insert into {SCHEMA}.{TABLE} "
            "(as_of, code_commit, silver_weeks, entered_at) "
            "values (?, ?, ?, sysutcdatetime())",
            [as_of, commit, weeks],
        )
    return weeks


def current_vintage() -> tuple[str | None, str, int, datetime] | None:
    """The newest marker row, or None if the table does not exist yet."""
    with fabric_io.connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "select count(*) from INFORMATION_SCHEMA.TABLES "
            "where table_schema = ? and table_name = ?",
            [SCHEMA, TABLE],
        )
        if cur.fetchone()[0] == 0:
            return None
        cur.execute(
            f"select top 1 as_of, code_commit, silver_weeks, entered_at "
            f"from {SCHEMA}.{TABLE} order by entered_at desc"
        )
        return cur.fetchone()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--as-of", metavar="DATE", help="go to this date (YYYY-MM-DD)")
    g.add_argument("--return", dest="ret", action="store_true", help="come back")
    g.add_argument("--status", action="store_true", help="what is loaded now")
    args = ap.parse_args()

    if args.status:
        row = current_vintage()
        if row is None or row[0] is None:
            print("warehouse holds CURRENT data"
                  + ("" if row is None else f" (since {row[3]:%Y-%m-%d %H:%M} UTC)"))
        else:
            print(f"warehouse holds VINTAGE {row[0]} — {row[2]} weeks in silver, "
                  f"code {row[1][:8]}, entered {row[3]:%Y-%m-%d %H:%M} UTC")
            print("return with: python pipeline/vintage.py --return")
        return 0

    # The guard protects a person's uncommitted work, not our own mess. Once a
    # vintage is loaded the seeds and the panel ARE modified, by this script, and
    # both --return and a hop to another date must still be possible. So consult
    # the marker first: dirty plus vintage is expected, dirty plus current is not.
    state = current_vintage()
    in_vintage = state is not None and state[0] is not None

    if not in_vintage and not working_tree_is_clean():
        print("seeds/ or research/data/ have uncommitted changes, and the "
              "warehouse holds current data — so this is your work, not a "
              "half-finished vintage. It rewrites both and restores them from "
              "git afterwards, so it refuses to run over anything uncommitted.",
              file=sys.stderr)
        return 1

    if args.ret:
        print("returning to current data")
        moved, _ = restore_seeds("HEAD")
        if moved:
            print(f"  restored from HEAD: {', '.join(moved)}")
        chain(None)
        weeks = mark(None)
        print(f"\nwarehouse holds CURRENT data — {weeks} weeks in silver")
        return 0

    try:
        target = date.fromisoformat(args.as_of)
    except ValueError:
        print(f"not a date: {args.as_of}", file=sys.stderr)
        return 1
    if target < HORIZON:
        print(f"{target} is before the snapshot horizon {HORIZON}. Every row has "
              "one version there, so a vintage would be today's data wearing a "
              "date.", file=sys.stderr)
        return 1
    if target > date.today():
        print(f"{target} is in the future", file=sys.stderr)
        return 1

    commit = commit_as_of(args.as_of)
    print(f"going to {target}; hand-written seeds from {commit[:8]}")
    moved, absent = restore_seeds(commit)
    print(f"  seeds that differ at that date: "
          f"{', '.join(moved) if moved else 'none — config has not changed since'}")
    if absent:
        print(f"  DID NOT EXIST on {target}, kept at HEAD: {', '.join(absent)}")
        print("  the vintage is approximate in exactly that way")
    chain(args.as_of)
    weeks = mark(args.as_of)
    print(f"\nwarehouse holds VINTAGE {target} — {weeks} weeks in silver")
    print("code is TODAY's, deliberately — see the module docstring")
    print("return with: python pipeline/vintage.py --return")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
