"""Fetch daily Brent (FRED `DCOILBRENTEU`) for research, on demand.

Brent left the weekly chain on 7 Sep 2026. It had never fed a model or a
forecast: it was acquired to settle one question — whether MBIE's weekly crude
number is Friday's quote or the Mon–Fri mean — and the answer is measured and
written down (`docs/research.md`: the Mon–Fri mean scores r = 0.89 against
0.68 for Friday). After that it sat in the warehouse as two columns of the
panel that nothing read, and in git as a 104 KB seed.

Keeping it as a committed seed was the wrong shape for a series FRED serves
under a stable id: the file is a cache of a public endpoint, and a cache does
not belong in version control. Keeping it in the weekly chain was wrong for a
different reason — nothing in that chain depends on it, and a step that
nothing depends on is a step that can only fail.

So it is here instead: run it when a question needs it. If Brent ever earns a
place in the weekly recompute — a second factor, a crack spread, a check on
MBIE's own crude column — this script moves to `pipeline/` and the reasoning
above is what has to change first.

Usage:  python research/fetch_brent.py            # -> data/brent_daily.csv
        python research/fetch_brent.py --weekly   # weekly Mon-Fri means

FRED runs a few days behind, so the newest week is an average of whatever days
exist. Nothing here is cached: the endpoint is small and public.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from io import StringIO
from pathlib import Path

import pandas as pd

SERIES = "DCOILBRENTEU"
URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}"
OUT = Path(__file__).parents[1] / "data" / "brent_daily.csv"


def fetch() -> pd.DataFrame:
    req = urllib.request.Request(
        URL, headers={"User-Agent": "nz-fuel-price-project research fetch"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode()

    # FRED writes missing days as "." — holidays, mostly.
    df = pd.read_csv(StringIO(raw), na_values=".")
    df.columns = ["date", "brent_usd_bbl"]
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna().reset_index(drop=True)


def weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Mon-Fri mean and range, stamped on the week's Friday.

    The same shape `export_panel.py` used to join, kept so that anyone
    reproducing an old panel column gets the same numbers.
    """
    d = daily.set_index("date")["brent_usd_bbl"]
    g = d.resample("W-FRI")
    return pd.DataFrame(
        {"brent_mean": g.mean(), "brent_range": g.max() - g.min()}
    ).dropna().reset_index(names="week_date")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weekly", action="store_true", help="aggregate to Mon-Fri weeks")
    args = ap.parse_args()

    daily = fetch()
    out = weekly(daily) if args.weekly else daily
    OUT.parent.mkdir(parents=True, exist_ok=True)
    path = OUT.with_name("brent_weekly.csv") if args.weekly else OUT
    out.to_csv(path, index=False)

    first, last = out.iloc[0, 0], out.iloc[-1, 0]
    print(f"{len(out)} rows, {first:%Y-%m-%d} .. {last:%Y-%m-%d} -> {path}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
