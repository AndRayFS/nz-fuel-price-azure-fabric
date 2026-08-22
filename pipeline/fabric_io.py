"""Shared plumbing for the weekly pipeline: the warehouse, and the Fabric REST API.

Two connections live here because the gate needs both and neither belongs to
it. `research/export_panel.py` carries its own copy of `connect()`; the two
converge when W5 moves that script into this package.

Auth mirrors ~/.dbt/profiles.yml (`authentication: CLI`) — an Azure CLI token.
W8 will swap AzureCliCredential for DefaultAzureCredential so one code path
serves both a local `az login` and a federated CI identity; nothing else here
should need to change.
"""

from __future__ import annotations

import json
import struct
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from itertools import chain, repeat

import mssql_python
from azure.identity import AzureCliCredential

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

FABRIC_API = "https://api.fabric.microsoft.com"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def connect():
    """A warehouse connection, authenticated with an Azure CLI token."""
    token = AzureCliCredential().get_token(SQL_SCOPE).token
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
    return AzureCliCredential().get_token(FABRIC_SCOPE).token


def _call(method: str, path: str, body: dict | None = None) -> dict:
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
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Fabric API {exc.code} on {path}: {detail}") from exc


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
