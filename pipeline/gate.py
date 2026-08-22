"""The freshness gate: the one thing in the weekly run allowed to stop it.

WHY. On 19 Aug 2026 the copy activity fetched the previous week's file from
MBIE's CDN and reported `Succeeded`. Bronze was truncated and reloaded with
stale content, `dbt run --full-refresh` and all 60 tests passed on it, and
Report 1 sat a week behind. Every layer we own is downstream of that one file,
so nothing below the ingest could tell. The only signal was the activity's own
row count, read by eye in the portal. This is that reading, automated.

WHAT IT IS NOT. The plan (workstreams.md, W3) called for an INDEPENDENT read:
download `weekly-table.csv` here and compare its newest week against bronze.
That turned out to be impossible from a script. mbie.govt.nz sits behind
Imperva, which serves a 212-byte JavaScript challenge to anything that is not
a browser: Python, curl over http/1.1 and http/2, full Chrome header sets and
a primed cookie jar all get the challenge, while Chrome from the SAME EGRESS
IP gets the file. It is a client check, not a network one, so a CI runner
would fare no better. Verified 22 Aug 2026.

So the gate asks what actually arrived instead of what was published:

  1. did the ingest run, recently, and finish;
  2. did what it read land in bronze intact;
  3. has the source grown since the week we last processed.

Check 3 is the stale-CDN detector. It cannot distinguish "MBIE has not
published yet" from "the CDN served us last week's file" — both look like a
source that did not grow — and it deliberately does not try. Both answers mean
the same thing here: do not run the chain. Which of the two it was is what the
AIP contour is for (`aip_latest_week_out_of_step`, W2), and that stays a
warning because we do not know AIP's publication regime well enough to stop on
it.

STATE. "The week we last processed" lives in `pipeline.processed_weeks`,
written by `mark_processed.py` at the end of the chain. Comparing against the
row count recorded THERE, rather than against the previous ingest run, is what
makes the gate safe to re-run: firing the ingest twice on the same fresh week
does not look like staleness, and a chain that failed halfway can be resumed.

CAPACITY. Every check needs the warehouse up. That is the accepted cost of
keeping the state in the warehouse: the W8 caveat about asking MBIE before
waking the capacity does not survive it, since there is no way to ask MBIE.

Exit codes:
    0  proceed — new data, and it landed
    2  nothing to do — no new week, or this week is already processed
    1  stop and look — the ingest did not run, failed, did not land, or the
       source moved in a way that needs a human

Usage:  python pipeline/gate.py [--max-run-age-hours 24] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import fabric_io

PROCEED, STOP, NOTHING_TO_DO = 0, 1, 2


def _age_hours(stamp: str, now: datetime) -> float:
    moment = datetime.fromisoformat(stamp.rstrip("Z")[:26]).replace(tzinfo=timezone.utc)
    return (now - moment).total_seconds() / 3600


def gather() -> dict:
    """Everything the decision needs, read from Fabric and from the warehouse.

    Deliberately takes no policy argument and makes no judgements: it collects
    even when the newest run failed, so that `decide` holds every branch in one
    readable place and can be replayed against past runs without a network.
    """
    runs = fabric_io.ingest_runs(6)
    run = runs[0] if runs else None
    rows_read = fabric_io.copy_rows_read(run) if run and run["status"] == "Completed" else None

    with fabric_io.connect() as conn:
        cur = conn.cursor()
        cur.execute("select max(cast(Date as date)), count(*) "
                    "from bronze_lakehouse.mbie.weekly_prices")
        bronze_week, bronze_rows = cur.fetchone()

        cur.execute("select count(*) from INFORMATION_SCHEMA.TABLES "
                    "where table_schema = 'pipeline' and table_name = 'processed_weeks'")
        if cur.fetchone()[0] == 0:
            marker_week = marker_rows = None
        else:
            cur.execute("select top 1 processed_week, ingest_rows_read "
                        "from pipeline.processed_weeks order by recorded_at desc")
            row = cur.fetchone()
            marker_week, marker_rows = row if row else (None, None)

    return {"run": run, "rows_read": rows_read,
            "bronze_week": bronze_week, "bronze_rows": bronze_rows,
            "marker_week": marker_week, "marker_rows": marker_rows,
            "now": datetime.now(timezone.utc)}


def decide(facts: dict, max_run_age_hours: float, stale_after_days: int = 14) -> dict:
    """The whole decision, as a verdict plus the numbers behind it. Pure."""
    run = facts["run"]
    if run is None:
        return {"verdict": "no_ingest_runs", "exit": STOP,
                "detail": "ingest_mbie_weekly has no run history at all"}

    if run["status"] != "Completed":
        return {"verdict": "ingest_not_completed", "exit": STOP,
                "detail": f"newest ingest run is {run['status']}",
                "run_started": run.get("startTimeUtc"),
                "failure_reason": run.get("failureReason")}

    age = _age_hours(run["startTimeUtc"], facts["now"])
    if age > max_run_age_hours:
        return {"verdict": "ingest_not_run", "exit": STOP,
                "detail": (f"newest ingest run is {age:.1f} h old, over the "
                           f"{max_run_age_hours:g} h limit — run it before the chain"),
                "run_started": run.get("startTimeUtc")}

    rows_read = facts["rows_read"]
    if rows_read is None:
        return {"verdict": "rows_read_unavailable", "exit": STOP,
                "detail": (f"no {fabric_io.COPY_ACTIVITY} row count on the newest run "
                           "— the activity was renamed, or the API changed shape"),
                "run_started": run.get("startTimeUtc")}

    bronze_week, bronze_rows = facts["bronze_week"], facts["bronze_rows"]
    marker_week, marker_rows = facts["marker_week"], facts["marker_rows"]

    seen = {"run_started": run.get("startTimeUtc"), "rows_read": rows_read,
            "bronze_rows": bronze_rows, "bronze_week": str(bronze_week),
            "last_processed_week": str(marker_week) if marker_week else None,
            "rows_read_then": marker_rows}

    # Did what the activity read actually land? A mismatch means the copy
    # succeeded and the write did not, which no downstream test would notice.
    if bronze_rows != rows_read:
        return {**seen, "verdict": "ingest_did_not_land", "exit": STOP,
                "detail": (f"the activity read {rows_read} rows but bronze holds "
                           f"{bronze_rows}")}

    if marker_week is None:
        return {**seen, "verdict": "no_marker_yet", "exit": PROCEED,
                "detail": ("pipeline.processed_weeks is empty — nothing to compare "
                           "against, so this run is allowed through")}

    if marker_rows is not None and rows_read < marker_rows:
        return {**seen, "verdict": "source_shrank", "exit": STOP,
                "detail": (f"the source read {rows_read} rows against {marker_rows} "
                           f"when {marker_week} was processed — MBIE dropped history, "
                           "or the fetch was truncated")}

    if bronze_week > marker_week and rows_read == marker_rows:
        return {**seen, "verdict": "weeks_replaced", "exit": STOP,
                "detail": (f"bronze ends on a newer week ({bronze_week}) but the row "
                           f"count is unchanged at {rows_read} — a week was removed as "
                           "another was added, which no test downstream would notice")}

    # No new week to process. Whether MBIE has yet to publish or the CDN served
    # last week's file, the answer is the same and the chain must not run;
    # telling the two apart is the AIP contour's job, at warn level.
    if bronze_week <= marker_week or rows_read == marker_rows:
        behind = (facts["now"].date() - marker_week).days
        # Normally not an alarm. It becomes one when it persists: a CDN that
        # keeps serving a stale copy looks identical week after week, and
        # answering "nothing to do" forever is the 19 Aug failure in slow
        # motion. Two missed publications is the line.
        if behind > stale_after_days:
            return {**seen, "verdict": "source_stuck", "exit": STOP,
                    "detail": (f"nothing new since {marker_week}, {behind} days ago — "
                               f"past the {stale_after_days}-day limit, so this is no "
                               "longer just an unpublished week")}
        return {**seen, "verdict": "nothing_new", "exit": NOTHING_TO_DO,
                "detail": (f"the source still holds {rows_read} rows and bronze still "
                           f"ends at {bronze_week}, as when {marker_week} was processed "
                           f"{behind} days ago")}

    return {**seen, "verdict": "ok", "exit": PROCEED,
            "detail": (f"new week {bronze_week}, "
                       f"{rows_read - marker_rows:+d} rows since {marker_week}")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-run-age-hours", type=float, default=24,
                    help="how recently ingest_mbie_weekly must have run (default 24)")
    ap.add_argument("--stale-after-days", type=int, default=14,
                    help="how long a source that has not grown stops being normal "
                         "and starts being a fault (default 14, two publications)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # Anything that stops the gate from reaching a verdict is itself a reason
    # not to run the chain. Fail closed, and say so in one line rather than a
    # traceback: the Fabric run APIs are flaky (see fabric_io.RETRIES), and a
    # transient outage must not read as a fault in the data.
    try:
        result = decide(gather(), args.max_run_age_hours, args.stale_after_days)
    except Exception as exc:  # noqa: BLE001 — the verdict is "we could not tell"
        result = {"verdict": "gate_check_failed", "exit": STOP,
                  "detail": f"{type(exc).__name__}: {exc}"}

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        stream = sys.stdout if result["exit"] == PROCEED else sys.stderr
        print(f"{result['verdict']}: {result['detail']}", file=stream)
        for key in ("run_started", "rows_read", "rows_read_then", "bronze_rows",
                    "bronze_week", "last_processed_week"):
            if key in result:
                print(f"  {key:<20} {result[key]}", file=stream)

    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
