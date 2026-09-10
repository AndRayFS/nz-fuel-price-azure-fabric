"""Shared plumbing for the weekly pipeline: the warehouse, and the Fabric REST API.

Two connections live here because the gate needs both and neither belongs to
it. `pipeline/export_panel.py` carries its own copy of `connect()`; the two
converge when W5 moves that script into this package.

Auth mirrors `profiles.yml` (`authentication: CLI`). Since W8 the credential
is DefaultAzureCredential, so one code path
serves both a local `az login` and a federated CI identity; nothing else here
should need to change.
"""

from __future__ import annotations

import json
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from itertools import chain, repeat

import mssql_python
from azure.identity import DefaultAzureCredential

# The warehouse, as in export_panel.py.
SERVER = (
    "fhi24zxnvquurfybnnzrkz22aq-ae4c5pcutjkedh2gfko4iqwk24"
    ".datawarehouse.fabric.microsoft.com"
)
DATABASE = "analytics_warehouse"
SQL_SCOPE = "https://database.windows.net/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256

# Fabric item ids, read once from /v1/workspaces and pinned here rather than
# looked up by display name every run: a renamed item should break loudly.
WORKSPACE_ID = "bc2e3801-9a54-4154-9f46-2a9dc442cad7"   # nz-fuel-price-project
PIPELINE_ID = "9584c5ac-340b-48bd-a05c-885e4ac31df6"    # ingest_mbie_weekly
COPY_ACTIVITY = "Copy_MBIE_weekly_data"
SQL_ENDPOINT_ID = "a2abcf3b-c492-42ca-aa16-3bac2db77a37"  # bronze_lakehouse

FABRIC_API = "https://api.fabric.microsoft.com"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# MBIE's `Date` column as a real date, accepting either format the source has
# used. It changed the whole file from `2026-08-21` to `28/08/2026` on
# 3 Sep 2026 without notice, and bronze is a verbatim copy. `try_cast` alone is
# worse than useless on the new form: days past the 12th fail, days up to it
# parse with day and month swapped.
#
# This is the twin of the `mbie_date` dbt macro, which is where the reasoning
# is written down. It cannot be shared — Jinja is not reachable from here — so
# the rule lives in exactly two places and every reader uses one of them.
# Unlike the macro this yields a `date`, not an ISO string: both callers want
# to compare it as a week, not to hand it to a model.
MBIE_DATE = ("coalesce(try_convert(date, [Date], 103), "
             "try_cast([Date] as date))")


def connect():
    """A warehouse connection, authenticated with an Entra token.

    DefaultAzureCredential rather than AzureCliCredential: locally it falls
    through to the `az login` this project has always used, and on a CI runner
    it picks up the federated identity without a second code path. Measured
    7 Sep 2026, the chain costs nothing — 0.35 s against 0.43 s for the CLI
    credential alone.
    """
    token = DefaultAzureCredential().get_token(SQL_SCOPE).token
    encoded = bytes(chain.from_iterable(zip(bytes(token, "UTF-8"), repeat(0))))
    token_bytes = struct.pack("<i", len(encoded)) + encoded
    # No DRIVER= clause: mssql-python bundles its own driver and rejects the
    # keyword outright.
    conn_str = (
        f"SERVER={SERVER},1433;DATABASE={DATABASE};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    return mssql_python.connect(
        conn_str,
        attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_bytes},
        autocommit=True,
    )


def _api_token() -> str:
    return DefaultAzureCredential().get_token(FABRIC_SCOPE).token


# `queryactivityruns` is flaky: measured 22 Aug 2026 at roughly one failure in
# ten identical calls with the capacity ACTIVE, in two shapes — HTTP 500
# `UnknownError`, and a refused connection. Neither says anything about the run
# being asked about, so both are retried. Without this the gate dies with a
# traceback on a healthy week, which is a false alarm dressed as a fault.
RETRIES = 4
BACKOFF_SECONDS = 2


def _call(method: str, path: str, body: dict | None = None) -> dict:
    """The response body. Headers are dropped — see `_call_full` when they matter."""
    return _call_full(method, path, body)[0]


def _call_full(
    method: str, path: str, body: dict | None = None
) -> tuple[dict, dict[str, str]]:
    """Body and headers.

    Starting a job answers 202 with an empty body and the run id only in
    `Location`, so that one caller needs the headers. Everything else reads
    the body and uses `_call`.
    """
    last: Exception | None = None

    for attempt in range(RETRIES):
        req = urllib.request.Request(
            f"{FABRIC_API}/{path.lstrip('/')}",
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {_api_token()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return (
                    json.loads(resp.read() or b"{}"),
                    {k.lower(): v for k, v in resp.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            last = RuntimeError(f"Fabric API {exc.code} on {path}: {detail}")
            # 4xx other than 429 is our fault and will not improve by asking
            # again — a wrong id, a renamed item, a token without the right role.
            if exc.code < 500 and exc.code != 429:
                raise last from exc
            wait = float(exc.headers.get("Retry-After") or BACKOFF_SECONDS * (attempt + 1))
        except urllib.error.URLError as exc:
            last = RuntimeError(f"Fabric API unreachable on {path}: {exc.reason}")
            wait = BACKOFF_SECONDS * (attempt + 1)

        if attempt < RETRIES - 1:
            print(f"  retrying in {wait:.0f}s ({last})", file=sys.stderr)
            time.sleep(wait)

    raise last  # type: ignore[misc]


# The fingerprint of bronze's CONTENT, as opposed to its size.
#
# The gate compares row counts, which cannot see a revision: MBIE restates
# published weeks by moving cents between `Importer cost` and `Importer
# margin`, and those two move in EXACT OPPOSITION — measured, all twelve
# groups net to zero (architecture.md). A plain `sum(Value)` would therefore
# be blind to the most common kind of revision this source produces. Hence a
# sum of squares alongside it: compensating edits change it.
#
# Decimal, never float. `Value` is text in bronze and has to be cast; casting
# to FLOAT makes the sum depend on summation order, so the same data could
# fingerprint differently between runs. decimal(38,6) is exact.
#
# `Status` is counted separately because a Provisional -> Final transition can
# leave every number untouched and still be a change worth rebuilding for.
BRONZE_FINGERPRINT_SQL = """
select
    count(*),
    sum(try_cast(Value as decimal(38,6))),
    sum(try_cast(Value as decimal(38,6)) * try_cast(Value as decimal(38,6))),
    sum(case when Status = 'Final' then 1 else 0 end)
from bronze_lakehouse.mbie.weekly_prices
"""


def bronze_fingerprint(cur) -> str | None:
    """A short string standing for what bronze currently holds.

    Compared as an opaque token: the gate only ever asks whether it equals the
    one recorded when the last week was processed.
    """
    cur.execute(BRONZE_FINGERPRINT_SQL)
    row = cur.fetchone()
    if row is None or row[0] is None:
        return None
    return "|".join("" if v is None else str(v) for v in row)


def _operation_status(url: str) -> str:
    """One poll of a long-running operation, by absolute URL.

    `_call` and `_call_full` prefix `FABRIC_API`, which is wrong here: the
    `Location` handed back by `refreshMetadata` points at a regional host
    (`wabi-…-redirect.analysis.windows.net`), not at `api.fabric.microsoft.com`.
    """
    req = urllib.request.Request(
        url, method="GET", headers={"Authorization": f"Bearer {_api_token()}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"{}").get("status", "Unknown")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"operation poll {exc.code}: {detail}") from exc


def refresh_sql_endpoint(timeout_seconds: int = 300) -> None:
    """Make the SQL analytics endpoint show what is already in the Lakehouse.

    A Lakehouse write and the T-SQL view over it are only eventually
    consistent, and nothing in T-SQL says which version you are reading. On
    10 Sep 2026 a table written at 00:15:33 was still invisible to
    `INFORMATION_SCHEMA` eight minutes later, and an overwrite of an existing
    table was still serving the previous version eight seconds after the copy
    reported Succeeded. Both were cured by this call in six to seven seconds.

    That is why it belongs at the end of the ingest rather than beside it: the
    ingest's contract is that bronze holds the file *and can be read*, and
    until this runs only the first half is true. Both readers of bronze — the
    gate and `snapshots/mbie_revisions.sql` — sit behind it.

    Measured cost is seconds. Waiting instead means paying for capacity for an
    interval nothing documents; 8 minutes was where the measurement stopped,
    not a ceiling.
    """
    _, headers = _call_full(
        "POST",
        f"/v1/workspaces/{WORKSPACE_ID}/sqlEndpoints/{SQL_ENDPOINT_ID}"
        "/refreshMetadata?preview=true",
        {},
    )
    operation = headers.get("location")
    if not operation:
        raise RuntimeError("refreshMetadata answered without a Location to poll")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = _operation_status(operation)
        if status == "Succeeded":
            return
        if status in {"Failed", "Undetermined"}:
            raise RuntimeError(f"endpoint metadata refresh ended as {status}")
        time.sleep(2)

    raise RuntimeError(
        f"endpoint metadata refresh still running after {timeout_seconds}s"
    )


def start_ingest() -> str:
    """Start `ingest_mbie_weekly`; returns the run id.

    The job API answers 202 with `Location:
    .../jobs/instances/<run id>` and no body, so the id is read off the header.
    """
    _, headers = _call_full(
        "POST",
        f"/v1/workspaces/{WORKSPACE_ID}/items/{PIPELINE_ID}/jobs/instances?jobType=Pipeline",
        body={},
    )
    location = headers.get("location", "")
    run_id = location.rstrip("/").rsplit("/", 1)[-1] if location else ""
    if not run_id:
        raise RuntimeError(
            f"the job started but no run id came back in Location: {headers!r}"
        )
    return run_id


def ingest_run(run_id: str) -> dict:
    """One job instance, by id."""
    return _call(
        "GET", f"/v1/workspaces/{WORKSPACE_ID}/items/{PIPELINE_ID}/jobs/instances/{run_id}"
    )


def ingest_runs(limit: int = 12) -> list[dict]:
    """Recent `ingest_mbie_weekly` job instances, newest first."""
    data = _call("GET", f"/v1/workspaces/{WORKSPACE_ID}/items/{PIPELINE_ID}/jobs/instances")
    runs = data.get("value", [])
    runs.sort(key=lambda r: r.get("startTimeUtc") or "", reverse=True)
    return runs[:limit]


def copy_rows_read(run: dict) -> int | None:
    """`rowsRead` off the copy activity of one run, or None if it has none.

    Two things about this endpoint were found by trying it, not by reading it:

    * activity detail hangs off `datapipelines/pipelineruns/{runId}` with the
      pipeline id ABSENT from the path — the three routes the item/job APIs
      suggest all return 404;
    * `lastUpdatedAfter` / `lastUpdatedBefore` are effectively mandatory.
      Omit them and the call still returns HTTP 200 with an EMPTY activity
      list, which reads exactly like "this run copied nothing". Hence the
      window derived from the run's own timestamps below.

    Verified 22 Aug 2026.
    """
    start = _iso(run.get("startTimeUtc"), -1)
    end = _iso(run.get("endTimeUtc") or run.get("startTimeUtc"), +1)
    data = _call(
        "POST",
        f"/v1/workspaces/{WORKSPACE_ID}/datapipelines/pipelineruns/{run['id']}/queryactivityruns",
        {
            "filters": [],
            "orderBy": [{"orderBy": "ActivityRunStart", "order": "DESC"}],
            "lastUpdatedAfter": start,
            "lastUpdatedBefore": end,
        },
    )
    for activity in data.get("value", []):
        if activity.get("activityName") == COPY_ACTIVITY:
            return (activity.get("output") or {}).get("rowsRead")
    return None


def _iso(stamp: str | None, day_offset: int) -> str:
    """A Fabric timestamp widened by a day, as the query window wants it."""
    if not stamp:
        raise RuntimeError("job instance carries no timestamp to window on")
    moment = datetime.fromisoformat(stamp.rstrip("Z")[:26]).replace(tzinfo=timezone.utc)
    return (moment + timedelta(days=day_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
