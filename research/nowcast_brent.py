"""Can the week in progress be seen before MBIE publishes it?

THE GAP. `pipeline/backtest.py` forecasts `d_net` from lags of `d_cost`, and
`adl_forecast` loops `for k in range(j, K + 1)` — at horizon j it drops every
coefficient on a cost change it cannot know yet. At h=1 that discards `b0`,
the largest single coefficient in the model: crude lands on `Importer cost` at
lag 0 (docs/research.md), and lag 0 is 26.3% of the petrol response. The model
is blind to the week in progress by construction, not by oversight.

WHY THAT WEEK IS PARTLY OBSERVABLE. `Importer cost` is a replacement cost —
this week's Singapore product spot at this week's FX, no purchase date, no
voyage (docs/mbie_notes.md). MBIE publishes week t on the Wednesday after it
ends, but the crude and FX underneath it trade daily and in public. By the
time the weekly chain runs, two or three trading days of the *next* week have
already happened.

WHAT THIS MEASURES. For each week, the change from last week's full Mon-Fri
mean of Brent-in-NZD to this week's mean over its first k trading days, and
how much of the week's actual `d_cost` that explains. k=5 is the ceiling — the
whole week, unobtainable at forecast time, and the honest upper bound on what
any crude proxy can do. k=1..3 is what is actually in hand.

WHAT IT DOES NOT MEASURE. Skill. R² is fit to points already known, and this
project has been burned by exactly that: `report1_ish` looked sound and was
withdrawn after the walk-forward test put it behind "the price won't move".
So the table also carries an expanding-window RMSE against the baseline the
model uses today, which is that the coming week's cost does not move.

BRENT IS NOT THE RIGHT BENCHMARK, it is the available one. The target is a
Singapore *product* quote; Brent is a crude one crack spread away, and Dubai —
the Asian crude MBIE actually publishes — has no free daily source at all
(FRED's series is monthly and two months stale). AIP republishes the exact
Argus product quote weekly, but on the Sunday of the week that has ENDED, so
it cannot reach the week in progress. Whatever is lost between crude and
product is inside every number below.

Usage:  python research/nowcast_brent.py [--from 2015] [--final-only]
Reads `data/panel_weekly.csv`; fetches daily Brent and NZD/USD and caches
them under `data/`. Offline apart from that fetch; no warehouse, no capacity.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
PANEL = ROOT / "data" / "panel_weekly.csv"

# Yahoo's chart endpoint is what their own site calls; it is undocumented and
# carries no stability promise. Fine for a measurement, a liability if the
# weekly chain ever depends on it — see the note this script's finding goes
# into. FRED is the documented alternative and is a week behind, which is
# precisely the thing being tested here, so it cannot serve.
YAHOO = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?period1=1104537600&period2=9999999999&interval=1d")
LITRES_PER_BBL = 158.987
FUELS = ("Diesel", "Regular Petrol", "Premium Petrol 95R")


def yahoo_daily(symbol: str, cache: Path) -> pd.Series:
    """Daily closes, cached. Refetched when the cache is older than a day."""
    fresh = cache.exists() and (
        dt.date.today() - dt.date.fromtimestamp(cache.stat().st_mtime)
    ).days < 1
    if not fresh:
        req = urllib.request.Request(
            YAHOO.format(sym=symbol), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read())
        res = payload["chart"]["result"][0]
        df = pd.DataFrame({
            "date": [dt.datetime.fromtimestamp(t, dt.UTC).date()
                     for t in res["timestamp"]],
            "close": res["indicators"]["quote"][0]["close"],
        }).dropna()
        df.to_csv(cache, index=False)
    df = pd.read_csv(cache, parse_dates=["date"])
    return df.set_index("date")["close"].sort_index()


def brent_nzd_cpl() -> pd.Series:
    """Brent in NZ cents per litre, daily.

    USD/bbl divided by USD-per-NZD gives NZD/bbl; the rest is unit conversion.
    Both legs come from the same source so that a day missing from one is
    missing from the other rather than silently mismatched.
    """
    brent = yahoo_daily("BZ=F", ROOT / "data" / "brent_daily_yahoo.csv")
    fx = yahoo_daily("NZDUSD=X", ROOT / "data" / "nzdusd_daily_yahoo.csv")
    both = pd.concat([brent.rename("usd"), fx.rename("nzdusd")],
                     axis=1, sort=True).dropna()
    return (both.usd / both.nzdusd) * 100.0 / LITRES_PER_BBL


def week_means(daily: pd.Series, stamps: pd.DatetimeIndex) -> pd.DataFrame:
    """Mean of the first k weekdays of each stamped week, k = 1..5.

    A stamp is the Friday sitting on the fifth day of its week
    (docs/mbie_notes.md), so Monday is stamp - 4 days. Days with no quote —
    holidays — are skipped rather than filled: the mean is over the trading
    days that existed, which is what a person reading a screen would have.
    """
    out = {}
    for k in range(1, 6):
        vals = []
        for f in stamps:
            lo, hi = f - pd.Timedelta(days=4), f - pd.Timedelta(days=5 - k)
            window = daily.loc[(daily.index >= lo) & (daily.index <= hi)]
            vals.append(window.mean() if len(window) else np.nan)
        out[f"m{k}"] = vals
    return pd.DataFrame(out, index=stamps)


def walk_forward(x: np.ndarray, y: np.ndarray, min_train: int = 52) -> tuple:
    """Expanding-window RMSE of a one-regressor fit, against predicting zero.

    Refit every week on everything before it, exactly as `backtest.py` does,
    so that no coefficient is ever informed by the week it predicts.
    """
    preds, actuals = [], []
    for t in range(min_train, len(x)):
        xs, ys = x[:t], y[:t]
        ok = np.isfinite(xs) & np.isfinite(ys)
        if ok.sum() < min_train or not np.isfinite(x[t]) or not np.isfinite(y[t]):
            continue
        A = np.column_stack([np.ones(ok.sum()), xs[ok]])
        beta = np.linalg.lstsq(A, ys[ok], rcond=None)[0]
        preds.append(beta[0] + beta[1] * x[t])
        actuals.append(y[t])
    if len(preds) < 20:
        return np.nan, np.nan, 0
    preds, actuals = np.array(preds), np.array(actuals)
    rmse = float(np.sqrt(np.mean((actuals - preds) ** 2)))
    base = float(np.sqrt(np.mean(actuals ** 2)))   # the model's present assumption
    return rmse, base, len(preds)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=2015,
                    help="first year (Yahoo's Brent contract starts 2015)")
    ap.add_argument("--final-only", action="store_true",
                    help="drop weeks whose importer_cost is still Provisional")
    args = ap.parse_args()

    crude = brent_nzd_cpl()
    print(f"Brent-in-NZD, daily: {crude.index.min():%F} .. {crude.index.max():%F}, "
          f"{len(crude)} days", file=sys.stderr)

    panel = pd.read_csv(PANEL, parse_dates=["Date"])
    panel = panel[panel.Date.dt.year >= args.start]

    print()
    print(f"{'fuel':<20} {'k':>2} {'n':>5} {'R2':>7} {'RMSE':>7} {'baseline':>9} {'gain':>7}")
    print("-" * 62)

    for fuel in FUELS:
        d = panel[panel.Fuel == fuel].sort_values("Date").reset_index(drop=True)
        if args.final_only:
            d = d[d.importer_cost_status == "Final"].reset_index(drop=True)
        stamps = pd.DatetimeIndex(d.Date)
        m = week_means(crude, stamps)

        y = d.importer_cost.diff().to_numpy()          # this week's actual move
        prev_full = m.m5.shift(1).to_numpy()           # last completed week

        for k in (1, 2, 3, 5):
            x = m[f"m{k}"].to_numpy() - prev_full
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 60:
                continue
            r = np.corrcoef(x[ok], y[ok])[0, 1]
            rmse, base, n_wf = walk_forward(x, y)
            gain = (1 - rmse / base) * 100 if np.isfinite(rmse) else np.nan
            tag = " <- whole week, not observable" if k == 5 else ""
            print(f"{fuel:<20} {k:>2} {ok.sum():>5} {r**2:>7.3f} "
                  f"{rmse:>7.3f} {base:>9.3f} {gain:>6.1f}%{tag}")
        print()

    print("R2 is in-sample fit; RMSE and baseline are walk-forward, c/L.",
          file=sys.stderr)
    print("baseline = predicting no cost move, which is what the model assumes "
          "today.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
