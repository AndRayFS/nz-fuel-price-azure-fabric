"""Offline walk-forward harness for the checks that followed the 19 Nov 2026
review of Report 1 (docs/research.md, "What an outside review of Report 1
asked, measured", 23 Nov 2026).

The production loop of `pipeline/backtest.py`, history only, with two things
made pluggable and nothing else changed:

  frames   what `bt.load` returns, per fuel — so a check can alter the panel
           (M5: cost without MBIE's fuel market adjustment);
  model    the fit and the forecast — so a check can alter the ECM term (M2).
           The default is production: `bt.fit_adl(with_ecm=True)` and
           `nowcast.forecast_with_nowcast`.

Brent and NZD/USD come from the cached daily files in data/ as they stand, and
are never refetched: `research/nowcast_brent.brent_nzd_cpl` refetches a cache
older than a day, which would make two runs of the same check disagree. Every
past week takes the three-day nowcast from settled history, as in production;
there is no live week and no guard here.

`reproduce()` is the plumbing check: the default model against
data/backtest_results.csv. `adl_ecm` must match exactly (same panel, no Brent);
`nowcast` may differ only where Yahoo has rewritten a bar since that run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import backtest as bt        # noqa: E402
import nowcast as nc         # noqa: E402

FUELS = ("Regular Petrol", "Diesel", "Premium Petrol 95R")


def cached_cpl() -> pd.Series:
    def one(name: str) -> pd.Series:
        s = pd.read_csv(ROOT / "data" / name, parse_dates=["date"])
        return s.set_index("date")["close"].sort_index()
    return nc.brent_nzd_cpl(one("brent_daily_yahoo.csv"), one("nzdusd_daily_yahoo.csv"))


@dataclass
class Model:
    """fit(d, upto) -> beta or None; fcst(d, t, beta, h, ncv) -> cumulative
    d_net over t+1..t+h, ncv being the nowcast for t+1 or nan (then the plain
    adl_ecm path)."""
    name: str
    fit: Callable
    fcst: Callable


def _prod_fit(d, upto):
    return bt.fit_adl(d, upto, with_ecm=True)


def _prod_fcst(d, t, beta, h, ncv):
    if np.isfinite(ncv):
        return nc.forecast_with_nowcast(d, t, beta, h, True, ncv)
    return bt.adl_forecast(d, t, beta, h, True)


PRODUCTION = Model("production", _prod_fit, _prod_fcst)


def walk_forward(frames: dict, model: Model = PRODUCTION, cpl: pd.Series | None = None,
                 t_from: pd.Timestamp | None = None,
                 t_to: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per (fuel, week of the call, horizon). `t_from`/`t_to` limit
    the weeks of the call that are computed, not the data the fit may use."""
    cpl = cached_cpl() if cpl is None else cpl
    rows = []
    for fuel, d in frames.items():
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        hi = (d.crude_vol_regime == "high").to_numpy()
        is_final = d.is_final.to_numpy()
        d_cost = d.d_cost.to_numpy()
        stamps = d.index.append(pd.DatetimeIndex([d.index[-1] + pd.Timedelta(days=7)]))
        x3 = nc.features(cpl, stamps)["x3"].to_numpy()
        for t in range(bt.MIN_TRAIN, n):
            when = d.index[t]
            if (t_from is not None and when < t_from) or (t_to is not None and when > t_to):
                continue
            beta = model.fit(d, t + 1)
            if beta is None:
                continue
            ncv = nc.nowcast_at(x3, d_cost, is_final, t)
            for h in bt.HORIZONS:
                actual = (retail[t + h] - retail[t]) if t + h < n else np.nan
                e = model.fcst(d, t, beta, h, np.nan)
                w = model.fcst(d, t, beta, h, ncv) if np.isfinite(ncv) else e
                rows.append(dict(
                    fuel=fuel, date=when, h=h, actual=actual, hi=bool(hi[t]),
                    price_now=retail[t],
                    target_date=d.index[t + h] if t + h < n else pd.NaT,
                    outcome_known=bool(np.isfinite(actual)),
                    adl_ecm=e * 1.15 if np.isfinite(e) else np.nan,
                    nowcast=w * 1.15 if np.isfinite(w) else np.nan,
                ))
    return pd.DataFrame(rows)


def production_frames() -> dict:
    return {fuel: bt.load(fuel) for fuel in FUELS}


def block_bootstrap_ci(values: np.ndarray, stat: Callable, block: int = 12,
                       reps: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Moving-block bootstrap of rows, 12-week blocks as elsewhere in
    docs/research.md. `values` is a 2-D array of rows; `stat` maps a resample
    to a number."""
    rng = np.random.default_rng(seed)
    n = len(values)
    starts = np.arange(n - block + 1)
    k = int(np.ceil(n / block))
    out = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.choice(starts, k)])[:n]
        out.append(stat(values[idx]))
    out = np.asarray(out, dtype=float)
    out = out[np.isfinite(out)]
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def reproduce() -> None:
    res = walk_forward(production_frames())
    ref = pd.read_csv(ROOT / "data" / "backtest_results.csv", parse_dates=["date"])
    m = res.merge(ref, on=["fuel", "date", "h"], suffixes=("", "_ref"))
    for col in ("adl_ecm", "nowcast"):
        diff = (m[col] - m[f"{col}_ref"]).abs()
        print(f"{col:8s} rows {len(m)}  max |diff| {diff.max():.2e}  "
              f"rows differing > 1e-9: {(diff > 1e-9).sum()}")


if __name__ == "__main__":
    reproduce()
