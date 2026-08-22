"""Replay the gate's decision against the runs that actually happened.

`decide` is pure, so every branch can be exercised without Fabric, the
warehouse or a network. The numbers below are the real ones, read from
`queryactivityruns` on 22 Aug 2026:

    06 Aug  34890      13 Aug  34920
    19 Aug  34920  <- served a week-old file, reported Succeeded
    19 Aug  34920  <- and again
    19 Aug  34950  <- after the cache-buster fix, +30 rows = one week

The first case is the point of the whole workstream: the run that passed 60
green tests and left Report 1 a week behind must not open the gate.

No pytest — the venv does not carry one, and pinning dependencies is W6.
Run it with `python pipeline/test_gate.py`; it prints one line per case and
exits non-zero on the first failure.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone

from gate import NOTHING_TO_DO, PROCEED, STOP, decide


def facts(*, rows_read, bronze_week, bronze_rows, marker_week, marker_rows,
          now, status="Completed", run_started="2026-08-19T04:36:11.3333333",
          vintage_as_of=None):
    return {
        "run": {"id": "r", "status": status, "startTimeUtc": run_started,
                "failureReason": None},
        "rows_read": rows_read,
        "bronze_week": bronze_week, "bronze_rows": bronze_rows,
        "marker_week": marker_week, "marker_rows": marker_rows,
        "vintage_as_of": vintage_as_of,
        "now": now,
    }


AUG19 = datetime(2026, 8, 19, 5, 0, tzinfo=timezone.utc)
AUG22 = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)

CASES = [
    # (name, facts, expected verdict, expected exit)
    ("a vintage warehouse stops the chain even when the week is perfect",
     facts(rows_read=34950, bronze_week=date(2026, 8, 14), bronze_rows=34950,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19,
           vintage_as_of=date(2026, 8, 13)),
     "warehouse_is_vintage", STOP),

    ("19 Aug, the stale fetch that reported Succeeded",
     facts(rows_read=34920, bronze_week=date(2026, 8, 7), bronze_rows=34920,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19,
           run_started="2026-08-19T04:26:37"),
     "nothing_new", NOTHING_TO_DO),

    ("19 Aug, the same fetch after the cache-buster fix",
     facts(rows_read=34950, bronze_week=date(2026, 8, 14), bronze_rows=34950,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19),
     "ok", PROCEED),

    ("13 Aug, an ordinary good week",
     facts(rows_read=34920, bronze_week=date(2026, 8, 7), bronze_rows=34920,
           marker_week=date(2026, 7, 31), marker_rows=34890,
           now=datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc),
           run_started="2026-08-13T07:44:52"),
     "ok", PROCEED),

    ("today: the chain already ran on this week",
     facts(rows_read=34950, bronze_week=date(2026, 8, 14), bronze_rows=34950,
           marker_week=date(2026, 8, 14), marker_rows=34950, now=AUG22,
           run_started="2026-08-22T08:00:00"),
     "nothing_new", NOTHING_TO_DO),

    ("a CDN stuck on the same file for three weeks",
     facts(rows_read=34920, bronze_week=date(2026, 8, 7), bronze_rows=34920,
           marker_week=date(2026, 8, 7), marker_rows=34920,
           now=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
           run_started="2026-08-28T07:00:00"),
     "source_stuck", STOP),

    ("the copy read more rows than landed in bronze",
     facts(rows_read=34950, bronze_week=date(2026, 8, 7), bronze_rows=34920,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19),
     "ingest_did_not_land", STOP),

    ("the ingest was not run before the chain",
     facts(rows_read=34950, bronze_week=date(2026, 8, 14), bronze_rows=34950,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG22,
           run_started="2026-08-19T04:36:11"),
     "ingest_not_run", STOP),

    ("the ingest failed",
     facts(rows_read=None, bronze_week=date(2026, 8, 7), bronze_rows=34920,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19,
           status="Failed"),
     "ingest_not_completed", STOP),

    ("MBIE dropped history",
     facts(rows_read=30000, bronze_week=date(2026, 8, 14), bronze_rows=30000,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19),
     "source_shrank", STOP),

    ("a week was removed as another was added",
     facts(rows_read=34920, bronze_week=date(2026, 8, 14), bronze_rows=34920,
           marker_week=date(2026, 8, 7), marker_rows=34920, now=AUG19),
     "weeks_replaced", STOP),

    ("first ever run, no marker to compare against",
     facts(rows_read=34950, bronze_week=date(2026, 8, 14), bronze_rows=34950,
           marker_week=None, marker_rows=None, now=AUG19),
     "no_marker_yet", PROCEED),
]


def main() -> int:
    failures = 0
    for name, given, want_verdict, want_exit in CASES:
        got = decide(given, max_run_age_hours=24)
        ok = got["verdict"] == want_verdict and got["exit"] == want_exit
        failures += not ok
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {name}\n     -> {got['verdict']} (exit {got['exit']})")
        if not ok:
            print(f"     expected {want_verdict} (exit {want_exit})")
    print(f"\n{len(CASES) - failures}/{len(CASES)} cases as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
