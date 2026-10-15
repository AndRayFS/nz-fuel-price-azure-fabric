"""Refresh Report 1's semantic model, so the chain has no Power BI step.

The model lives in My Workspace, and that is why this goes through a Fabric
pipeline rather than a call from here. The runner's identity is a service
principal, and My Workspace does not admit service principals at all. The
pipeline `refresh_report_1` holds a connection signed in as the model's
owner, and its one Web activity posts an enhanced refresh to
`/v1.0/myorg/datasets/<id>/refreshes` under that account.

Two obvious routes do not work, both measured 15 Oct 2026
(architecture.md, "Refreshing Report 1 from the chain"):

  * the pipeline's own "Semantic model refresh" activity addresses the model
    through `/groups/<workspace>/…`, which a personal workspace answers with
    401 `GroupNotAccessible`;
  * a scheduled refresh in Power BI starts up to an hour late and reports to
    no one the runner can see.

The Web activity follows the async pattern on its own: it polls the refresh
until it ends and returns the final status, and the pipeline's If condition
fails the run unless that status is `Completed`. So a green run here is a
refreshed model, not an accepted request.

Usage:  python pipeline/run_refresh.py [--timeout-minutes 15]

Exit codes: 0 refreshed, 1 failed or timed out. The timeout does not cancel
the run — it stops waiting, and the pipeline carries on in Fabric.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from fabric_io import REFRESH_PIPELINE_ID, pipeline_run, start_pipeline

POLL_SECONDS = 10

# Unlike the ingest, `Deduped` is not success here: it means another refresh
# was already in flight, and its outcome is not this run's to report.
DONE = {"Completed", "Failed", "Cancelled", "Deduped"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-minutes", type=int, default=15)
    args = ap.parse_args()

    run_id = start_pipeline(REFRESH_PIPELINE_ID)
    print(f"refresh started, run {run_id}", file=sys.stderr)

    deadline = time.time() + args.timeout_minutes * 60
    state, info = "NotStarted", {}
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        info = pipeline_run(REFRESH_PIPELINE_ID, run_id)
        state = info.get("status", "Unknown")
        if state in DONE:
            break
        print(f"  {state} …", file=sys.stderr)

    if state == "Completed":
        print("Report 1's model refreshed", file=sys.stderr)
        return 0
    if state in DONE:
        print(f"refresh ended as {state}", file=sys.stderr)
        if info.get("failureReason"):
            print(json.dumps(info["failureReason"], indent=1), file=sys.stderr)
        return 1

    print(f"stopped waiting after {args.timeout_minutes} min; the run is still "
          f"{state} in Fabric and was NOT cancelled", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
