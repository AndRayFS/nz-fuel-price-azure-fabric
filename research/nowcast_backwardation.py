"""Does the nowcast survive the 2026 backwardation? Futures, spot and ComCom.

`research/nowcast_in_adl.py` scored the nowcast on Yahoo front-month Brent
futures (`BZ=F`) over 2010-2026, almost all of it a market in which futures
and physical spot agree. From September 2026 they did not: spot ran up to 25%
above futures (`docs/research.md`, "The nowcast's Brent is futures"). That
section made shipping conditional on re-measuring on spot, or on measuring how
much of the edge survives on futures. This is that measurement.

PRE-REGISTERED, written 5 Nov 2026 before any number here was computed:

  Sample   Diesel and Regular Petrol, h=1 and h=2, forecast origins t whose
           nowcast week t+1 is stamped 2026-09-04 or later, through the last
           week with a known outcome in the published archive dated
           2026-11-05 (MBIE weeks to 30 Oct).
  Method   `nowcast_in_adl.py` defaults (3 trading days, expanding Final-only
           nowcast regression, min 52) on the unchanged ADL+ECM.
  PASS     pooled MAE of adl_ecm + futures nowcast <= adl_ecm at h=1 AND h=2.
  FAIL     worse at either. PASS opens production on futures, with fallback;
           FAIL shelves the nowcast.

Diagnostics, reported and not deciding: the same nowcast on FRED
`DCOILBRENTEU` spot (same Yahoo FX, so only the crude leg differs); on
ComCom's daily `REFINED_COSTS` (history starts 1 Feb 2026, so its regression
is fit on all pairs up to t, min 8, with no Final filter — a different
fitting rule); the cost-level error of each; and the Mar-Aug 2026 crisis weeks
before the backwardation.

PLUMBING. The panel is the published archive's `weekly_prices.csv` and the
flags come from its `forecasts.csv`, so the run needs no warehouse. The
reproduced `adl_ecm` is checked against the archive's own `pred_adl_ecm`
before anything is read; on 5 Nov the largest difference was 0.00005 c/L.

Usage:  python research/nowcast_backwardation.py [--archive-date 2026-11-05]
Fetches the archive, Yahoo, FRED and ComCom once into
data/nowcast_backwardation/ and reads the cache after that. Delete the folder
to refetch. No warehouse, no capacity.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "research"))

import backtest as bt                                            # noqa: E402
from nowcast_brent import LITRES_PER_BBL, YAHOO, week_means      # noqa: E402
from nowcast_in_adl import NC_MIN_TRAIN, forecast_with_nowcast   # noqa: E402

CACHE = ROOT / "data" / "nowcast_backwardation"
ARCHIVE = "https://nzfueldata.blob.core.windows.net/data/{d}/nz-fuel-{d}.zip"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
COMCOM = ("https://www.comcom.govt.nz/assets/Uploads/"
          "Fuel-price-monitoring-Data-to-27-October-2026.xlsx")

DAYS = 3
FUELS = ("Diesel", "Regular Petrol")
SAMPLE_FROM = pd.Timestamp("2026-09-04")
PRE_FROM, PRE_TO = pd.Timestamp("2026-03-06"), pd.Timestamp("2026-08-28")
METHODS = ["naive", "adl_ecm", "nc_fut", "nc_spot", "nc_cc"]


def fetch(url: str, name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def yahoo(symbol: str) -> pd.Series:
    raw = fetch(YAHOO.format(sym=symbol), f"yahoo_{symbol}.json").read_text()
    res = json.loads(raw)["chart"]["result"][0]
    s = pd.Series(res["indicators"]["quote"][0]["close"], index=pd.to_datetime(
        [dt.datetime.fromtimestamp(t, dt.UTC).date() for t in res["timestamp"]]))
    return s.dropna().sort_index()


def nzd_cpl(usd: pd.Series, fx: pd.Series) -> pd.Series:
    both = pd.concat([usd.rename("usd"), fx.rename("fx")], axis=1, sort=True).dropna()
    return both.usd / both.fx * 100.0 / LITRES_PER_BBL


def feature(daily: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    """This week's first DAYS trading days against last week's full week."""
    m = week_means(daily, index)
    return (m[f"m{DAYS}"] - m.m5.shift(1)).to_numpy()


def nowcast(x, y, final, t, final_only: bool, min_n: int) -> float:
    """Refit on pairs up to and including t, apply to t+1 (as nowcast_in_adl)."""
    if t + 1 >= len(x) or not np.isfinite(x[t + 1]):
        return np.nan
    ok = np.isfinite(x[:t + 1]) & np.isfinite(y[:t + 1])
    if final_only:
        ok &= final[:t + 1]
    if ok.sum() < min_n:
        return np.nan
    A = np.column_stack([np.ones(ok.sum()), x[:t + 1][ok]])
    g = np.linalg.lstsq(A, y[:t + 1][ok], rcond=None)[0]
    return g[0] + g[1] * x[t + 1]


def mae(s: pd.DataFrame, m: str) -> float:
    return np.abs(s[m] - s.actual).mean() if s[m].notna().all() else np.nan


def table(sub: pd.DataFrame, title: str) -> None:
    print(f"\n{title}\nMAE c/L on the pump price")
    print(f"  {'fuel':<15}{'h':>2}{'n':>4} " + "".join(f"{m:>9}" for m in METHODS)
          + f"{'fut vs ecm':>12}")
    for h in (1, 2):
        for fuel in (*FUELS, "POOLED"):
            s = sub[sub.h == h] if fuel == "POOLED" else sub[(sub.h == h) & (sub.fuel == fuel)]
            s = s.dropna(subset=["actual", "adl_ecm", "nc_fut"])
            if s.empty:
                continue
            v = {m: mae(s, m) for m in METHODS}
            print(f"  {fuel:<15}{h:>2}{len(s):>4} " + "".join(f"{v[m]:>9.3f}" for m in METHODS)
                  + f"{(1 - v['nc_fut'] / v['adl_ecm']) * 100:>11.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05",
                    help="the published load archive to read (its date, not the data's)")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    zpath = fetch(ARCHIVE.format(d=args.archive_date), f"nz-fuel-{args.archive_date}.zip")
    with zipfile.ZipFile(zpath) as z:
        wp = pd.read_csv(io.BytesIO(z.read("weekly_prices.csv")))
        fc = pd.read_csv(io.BytesIO(z.read("forecasts.csv")), parse_dates=["week_date"])
    wp.rename(columns={"week_date": "Date", "fuel": "Fuel"}).to_csv(
        CACHE / "panel_weekly.csv", index=False)
    (fc[fc.horizon_weeks == 1][["week_date", "fuel", "crude_vol_regime",
                                "crude_episode_id", "crude_move_regime"]]
     .drop_duplicates(["week_date", "fuel"]).to_csv(CACHE / "period_flags.csv", index=False))
    bt.PANEL, bt.FLAGS = CACHE / "panel_weekly.csv", CACHE / "period_flags.csv"

    fx = yahoo("NZDUSD=X")
    fut = yahoo("BZ=F")
    spot = pd.read_csv(fetch(FRED, "fred_DCOILBRENTEU.csv"), na_values=".").dropna()
    spot = pd.Series(spot.iloc[:, 1].to_numpy(), index=pd.to_datetime(spot.iloc[:, 0])).sort_index()
    cc = pd.read_excel(fetch(COMCOM, "comcom_daily.xlsx"))
    cc["DATE"] = pd.to_datetime(cc.DATE, dayfirst=True)
    cc_daily = {f: cc[cc.FUEL_TYPE == code].set_index("DATE").REFINED_COSTS.sort_index()
                for f, code in (("Diesel", "Diesel"), ("Regular Petrol", "91"))}
    daily = {"fut": nzd_cpl(fut, fx), "spot": nzd_cpl(spot, fx)}

    rows, cost_rows = [], []
    for fuel in FUELS:
        d = bt.load(fuel)
        idx = pd.DatetimeIndex(d.index)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        y = d.d_cost.to_numpy()
        final = d.is_final.to_numpy()
        X = {"fut": feature(daily["fut"], idx), "spot": feature(daily["spot"], idx),
             "cc": feature(cc_daily[fuel], idx)}
        for t in range(int(np.searchsorted(idx, pd.Timestamp("2026-01-01"))), n - 1):
            b = bt.fit_adl(d, t + 1, with_ecm=True)
            if b is None:
                continue
            nc = {"fut": nowcast(X["fut"], y, final, t, True, NC_MIN_TRAIN),
                  "spot": nowcast(X["spot"], y, final, t, True, NC_MIN_TRAIN),
                  "cc": nowcast(X["cc"], y, final, t, False, 8)}
            cost_rows.append(dict(fuel=fuel, nc_week=idx[t + 1], d_cost=y[t + 1],
                                  **{f"dc_{k}": v for k, v in nc.items()}))
            for h in (1, 2):
                e = bt.adl_forecast(d, t, b, h, True)
                r = dict(fuel=fuel, date=idx[t], nc_week=idx[t + 1], h=h,
                         price_now=retail[t], naive=0.0, adl_ecm=e * 1.15,
                         actual=retail[t + h] - retail[t] if t + h < n else np.nan)
                for k, v in nc.items():
                    f = forecast_with_nowcast(d, t, b, h, True, v) if np.isfinite(v) else np.nan
                    r[f"nc_{k}"] = f * 1.15 if np.isfinite(f) else np.nan
                rows.append(r)
    res, cost = pd.DataFrame(rows), pd.DataFrame(cost_rows)

    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    chk = res.merge(pub[["date", "fuel", "h", "pred_adl_ecm"]], on=["date", "fuel", "h"])
    gap = (chk.price_now + chk.adl_ecm - chk.pred_adl_ecm).abs().max()
    print(f"PLUMBING: {len(chk)} rows, max |reproduced - published pred_adl_ecm| = {gap:.6f} c/L")
    if not gap < 0.01:
        print("  does not reproduce production; nothing below can be read", file=sys.stderr)
        return 1

    sf = pd.concat([spot.rename("spot"), fut.rename("fut")], axis=1, sort=True).dropna()
    wk = sf[sf.index >= "2026-08-24"].resample("W-FRI").mean()
    wk["gap_pct"] = (wk.spot / wk.fut - 1) * 100
    print("\nSpot over futures, weekly mean of daily USD/bbl:")
    print(wk.round(2).to_string())

    prim = res[(res.nc_week >= SAMPLE_FROM) & res.actual.notna()]
    pre = res[(res.nc_week >= PRE_FROM) & (res.nc_week <= PRE_TO) & res.actual.notna()]
    table(prim, "PRIMARY - nowcast week from 2026-09-04 (backwardation)")
    table(pre, "DIAGNOSTIC - crisis before backwardation, nowcast week 2026-03-06..2026-08-28")

    print("\nDECISION (pre-registered): pooled MAE nc_fut <= adl_ecm at h=1 AND h=2")
    passed = []
    for h in (1, 2):
        s = prim[prim.h == h].dropna(subset=["adl_ecm", "nc_fut"])
        a, f = mae(s, "adl_ecm"), mae(s, "nc_fut")
        passed.append(f <= a)
        print(f"  h={h}: adl_ecm {a:.3f}  nc_fut {f:.3f}  -> {'not worse' if f <= a else 'WORSE'}")
    print(f"  => {'PASS' if all(passed) else 'FAIL'}")

    print("\nCost level: mean |nowcast - actual d_cost|, c/L ('zero' is today's assumption)")
    for label, lo, hi in (("backwardation", SAMPLE_FROM, pd.Timestamp.max),
                          ("crisis before it", PRE_FROM, PRE_TO)):
        c = cost[(cost.nc_week >= lo) & (cost.nc_week <= hi) & cost.d_cost.notna()]
        for fuel in FUELS:
            cf = c[c.fuel == fuel]
            parts = [f"zero {cf.d_cost.abs().mean():6.2f}"] + [
                f"{k} {(cf[f'dc_{k}'] - cf.d_cost).abs().mean():6.2f} "
                f"(n={(cf[f'dc_{k}'] - cf.d_cost).notna().sum()})" for k in ("fut", "spot", "cc")]
            print(f"  {label:<18}{fuel:<15}" + "  ".join(parts))

    w = prim[prim.h == 1].merge(cost, on=["fuel", "nc_week"])
    for m in ("adl_ecm", "nc_fut", "nc_spot", "nc_cc"):
        w[f"err_{m}"] = (w[m] - w.actual).round(2)
    print("\nWeek by week, backwardation sample, h=1 (error = forecast - actual, c/L)")
    print(w[["fuel", "nc_week", "actual", "err_adl_ecm", "err_nc_fut", "err_nc_spot",
             "err_nc_cc", "d_cost", "dc_fut", "dc_spot", "dc_cc"]]
          .round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
