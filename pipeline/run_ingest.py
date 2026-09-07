"""Start `ingest_mbie_weekly` and wait for it, so the chain has no portal step.

Step 0 of the weekly chain used to be a person opening the Fabric portal and
clicking Run on the pipeline. That is the last manual action before the gate,
and CI cannot click. This starts the same pipeline through the Fabric job API
and polls until it finishes.

It deliberately does NOT judge the result beyond success or failure: whether
the run actually brought a new week is the gate's question, and the gate reads
`rowsRead` off the copy activity to answer it. A pipeline reporting `Succeeded`
on a week-old file out of MBIE's CDN is exactly the 19 Aug 2026 failure, and
this script would call that a success. Run the gate afterwards; never treat a
green run here as a green week.

Usage:  python pipeline/run_ingest.py [--timeout-minutes 20]

Exit codes: 0 finished, 1 failed or timed out. The timeout does not cancel the
run — it stops waiting, and the pipeline carries on in Fabric.
"""

from __future__ import annotations

import argparse
import sys
import time

from fabric_io import ingest_run, start_ingest

POLL_SECONDS = 15

# Fabric reports these as terminal. `Deduped` appears when an identical run is
# already in flight and Fabric refuses to start a second one — not an error,
# and not something to retry into.
DONE = {"Completed", "Failed", "Cancelled", "Deduped"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-minutes", type=int, default=20)
    args = ap.parse_args()

    run_id = start_ingest()
    print(f"ingest started, run {run_id}", file=sys.stderr)

    deadline = time.time() + args.timeout_minutes * 60
    state = "NotStarted"
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        info = ingest_run(run_id)
        state = info.get("status", "Unknown")
        if state in DONE:
            break
        print(f"  {state} …", file=sys.stderr)

    if state == "Completed":
        print("ingest finished — now run the gate, which decides whether the "
              "file it brought is actually a new week", file=sys.stderr)
        return 0
    if state == "Deduped":
        print("Fabric refused a second run because one was already in flight; "
              "treating that as done", file=sys.stderr)
        return 0
    if state in DONE:
        print(f"ingest ended as {state}", file=sys.stderr)
        return 1

    print(f"stopped waiting after {args.timeout_minutes} min; the run is still "
          f"{state} in Fabric and was NOT cancelled", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
