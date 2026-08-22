"""Close the weekly run: record which week was processed, and on what.

This is the state the gate needs and nothing else in the project holds. The
alternative considered was reading `max(week_date)` from `forecast_accuracy` —
no new object, and today the two agree exactly — but that couples the decision
"may the chain run" to a report table that exists for a different reason and
could be rebuilt, filtered or repointed without anyone thinking about the gate.
A row here says only what it means (workstreams.md, open question 6).

Append-only, one row per completed run. History is cheap and answers "when did
we last process, and what did the ingest read that day" without a snapshot.

Run it as the LAST step of the weekly chain — after `forecast_accuracy` is
rebuilt. Running it earlier marks a week as processed that is not.
"""

from __future__ import annotations

import sys

import fabric_io

SCHEMA = "pipeline"
TABLE = "processed_weeks"

DDL = f"""
create table {SCHEMA}.{TABLE} (
    processed_week   date         not null,
    bronze_rows      bigint       not null,
    ingest_run_id    varchar(64)      null,
    ingest_rows_read bigint           null,
    recorded_at      datetime2(3) not null
)
"""


def ensure_table(cur) -> None:
    """Create schema and table if they are not there yet.

    Fabric Warehouse has no `create ... if not exists`, and whether it accepts
    dynamic SQL is a question this does not need to answer: ask
    INFORMATION_SCHEMA in Python and issue plain DDL only when it is missing.
    """
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


def main() -> int:
    runs = fabric_io.ingest_runs(1)
    run = runs[0] if runs else None
    rows_read = fabric_io.copy_rows_read(run) if run else None

    with fabric_io.connect() as conn:
        cur = conn.cursor()
        ensure_table(cur)

        cur.execute(
            "select max(cast(Date as date)), count(*) "
            "from bronze_lakehouse.mbie.weekly_prices"
        )
        processed_week, bronze_rows = cur.fetchone()

        if processed_week is None:
            print("bronze is empty — nothing to mark", file=sys.stderr)
            return 1

        cur.execute(
            f"insert into {SCHEMA}.{TABLE} "
            "(processed_week, bronze_rows, ingest_run_id, ingest_rows_read, recorded_at) "
            "values (?, ?, ?, ?, sysutcdatetime())",
            [processed_week, bronze_rows, (run or {}).get("id"), rows_read],
        )

    print(
        f"marked {processed_week} processed "
        f"({bronze_rows} bronze rows, ingest read {rows_read})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
