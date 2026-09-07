"""Write a dataframe to the warehouse, so derived data stops travelling in git.

Three files used to reach the warehouse by being written to disk, committed,
and loaded by `dbt seed`: the forecast history, the regime flags and the AIP
store. That route made git the transport for data nobody writes by hand, and
under CI it made every weekly run a bot commit. Configuration still belongs in
git — `periods.csv` and `variable_mapping.csv` are hand-drawn and their history
is the point (architecture.md, "Observations belong in the warehouse,
configuration belongs in git").

Two write modes, and the difference matters more than it looks:

`replace` — for tables that are a pure function of their inputs. The forecast
history and the regime flags are rebuilt from the panel every week, so losing
one costs a recompute and nothing else. Truncate, then insert.

`append_new` — for a table that IS the history. The AIP store accumulates
weeks the source itself deletes: AIP keeps 11-15 reports and Mar-Jun 2026 is
already gone from its site. Nothing upstream can rebuild it, so it is never
truncated; rows are matched on a key and only new ones are inserted. This is
the one that `dbt seed --full-refresh` used to truncate and reload every
single week from a file — the risk that motivated all of this.
"""

from __future__ import annotations

import sys

import pandas as pd

import fabric_io

# SQL Server allows 2100 parameters per statement; stay well under it, and
# under Fabric's own row-per-VALUES limits, by sizing the batch to the width.
MAX_PARAMS = 1800


def _batch_size(n_cols: int) -> int:
    return max(1, min(500, MAX_PARAMS // max(1, n_cols)))


def _values(df: pd.DataFrame) -> list[list]:
    """Rows as plain Python, with NaN/NaT flattened to None.

    pandas types do not survive the driver: NaN is a float that SQL Server
    stores as a number rather than a null, and Timestamp is not a date.
    """
    out = []
    for row in df.itertuples(index=False, name=None):
        vals = []
        for v in row:
            # `pd.isna` on any scalar, not just float. pandas 3 stores a
            # missing string as pd.NA, which is not a float and slipped
            # through an earlier isinstance check — the rows then reached the
            # warehouse as EMPTY STRINGS rather than NULLs. Caught by
            # comparing against the table dbt seed used to build: 3,087 nulls
            # there, 3,087 empty strings here.
            if v is None or (pd.api.types.is_scalar(v) and pd.isna(v)):
                vals.append(None)
            elif isinstance(v, pd.Timestamp):
                vals.append(v.to_pydatetime().date())
            else:
                vals.append(v.item() if hasattr(v, "item") else v)
        out.append(vals)
    return out


def ensure_table(cur, schema: str, table: str, ddl: str) -> None:
    """Create the schema and table when missing.

    Fabric Warehouse has no `create ... if not exists`; ask INFORMATION_SCHEMA
    and issue plain DDL, the way `mark_processed.py` does.
    """
    cur.execute(
        "select count(*) from INFORMATION_SCHEMA.SCHEMATA where schema_name = ?",
        [schema],
    )
    if cur.fetchone()[0] == 0:
        cur.execute(f"create schema {schema}")

    cur.execute(
        "select count(*) from INFORMATION_SCHEMA.TABLES "
        "where table_schema = ? and table_name = ?",
        [schema, table],
    )
    if cur.fetchone()[0] == 0:
        cur.execute(ddl)


def _insert(cur, schema: str, table: str, df: pd.DataFrame) -> int:
    cols = list(df.columns)
    placeholders = "(" + ", ".join("?" * len(cols)) + ")"
    stmt_head = f"insert into {schema}.{table} ({', '.join(cols)}) values "
    rows = _values(df)
    size = _batch_size(len(cols))

    for i in range(0, len(rows), size):
        chunk = rows[i:i + size]
        stmt = stmt_head + ", ".join([placeholders] * len(chunk))
        flat = [v for r in chunk for v in r]
        cur.execute(stmt, flat)
    return len(rows)


def replace(df: pd.DataFrame, schema: str, table: str, ddl: str) -> int:
    """Truncate and reload. Only for tables that can be rebuilt from inputs."""
    with fabric_io.connect() as conn:
        cur = conn.cursor()
        ensure_table(cur, schema, table, ddl)
        cur.execute(f"truncate table {schema}.{table}")
        n = _insert(cur, schema, table, df)
    print(f"{schema}.{table}: replaced with {n} rows", file=sys.stderr)
    return n


def append_new(
    df: pd.DataFrame, schema: str, table: str, ddl: str, key: list[str]
) -> int:
    """Insert only rows whose key is not in the table. Never truncates.

    Returns the number inserted. Re-running on unchanged input inserts nothing,
    which is what makes the weekly chain safe to repeat.
    """
    with fabric_io.connect() as conn:
        cur = conn.cursor()
        ensure_table(cur, schema, table, ddl)

        cur.execute(f"select {', '.join(key)} from {schema}.{table}")
        existing = {tuple(r) for r in cur.fetchall()}

        if existing:
            incoming = _values(df[key])
            fresh = df[[tuple(k) not in existing for k in incoming]]
        else:
            fresh = df

        if fresh.empty:
            print(f"{schema}.{table}: nothing new", file=sys.stderr)
            return 0

        n = _insert(cur, schema, table, fresh)

    print(f"{schema}.{table}: appended {n} rows, {len(existing)} already there",
          file=sys.stderr)
    return n
