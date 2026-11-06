"""How much would seeing this week's pump price be worth? A ceiling, on ComCom.

When the weekly run makes its calls, on the Wednesday after a week ends, the
next week has already begun at the pump. A timely daily retail source would
show part of the very week the one-week call is about. The only timely one
found is Gaspy, crowd-sourced and unlicensed (`docs/research.md`, "Sources
checked for a timely series"). Before asking about its rights, this measures
the prize on the Commerce Commission's daily national average, which exists
from 1 Feb 2026 but is published fortnightly and so could never feed a run.

PRE-REGISTERED, written 5 Nov 2026 before any number here was computed:

  Primary  "direct": the change from ComCom's mean over week t (Mon-Sun) to
           its mean over the first two days (Mon-Tue) of week t+1, taken as
           the forecast of MBIE's one-week change in `adjusted_retail_price`.
           No fitting. Two days, because at the Wednesday run Monday and
           Tuesday are complete and Wednesday is not.
  Against  production's one-week call (`pred_adl_ecm` in the archive).
  Sample   every origin whose two weeks ComCom covers, with an outcome:
           Diesel and Regular Petrol (ComCom "91"), pooled, h=1.
  WORTH PURSUING a timely source if MAE(direct) is at least 20% below
           MAE(production). Otherwise not worth the licensing question.

  Diagnostics, not deciding: three days (Mon-Wed); a walk-forward
  regression of the actual change on production's call and the two-day
  reading (all earlier pairs, min 8); per fuel; how closely ComCom's weekly
  mean tracks MBIE's weekly price.

CAVEATS. Every origin is in 2026 and almost all inside one volatility episode.
ComCom's retail is a third party's crowd-sourced average, not MBIE's
Datamine series; the validity check prints how close they are. This is a
ceiling on the information, not a plan for a source.

Usage:  python research/retail_ceiling.py [--archive-date 2026-11-05]
Fetches the archive and ComCom's file once into data/retail_ceiling/.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
CACHE = ROOT / "data" / "retail_ceiling"
ARCHIVE = "https://nzfueldata.blob.core.windows.net/data/{d}/nz-fuel-{d}.zip"
COMCOM = ("https://www.comcom.govt.nz/assets/Uploads/"
          "Fuel-price-monitoring-Data-to-27-October-2026.xlsx")
FUELS = {"Diesel": "Diesel", "Regular Petrol": "91"}
MIN_FIT = 8
THRESHOLD = 0.20


def fetch(url: str, name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def window_mean(daily: pd.Series, lo: pd.Timestamp, hi: pd.Timestamp) -> float:
    w = daily[(daily.index >= lo) & (daily.index <= hi)]
    return float(w.mean()) if len(w) else np.nan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05")
    args = ap.parse_args()
    with zipfile.ZipFile(fetch(ARCHIVE.format(d=args.archive_date),
                               f"nz-fuel-{args.archive_date}.zip")) as z:
        fc = pd.read_csv(io.BytesIO(z.read("forecasts.csv")), parse_dates=["week_date"])
    cc = pd.read_excel(fetch(COMCOM, "comcom_daily.xlsx"))
    cc["DATE"] = pd.to_datetime(cc.DATE, dayfirst=True)
    last_day = cc.DATE.max()

    rows = []
    for fuel, code in FUELS.items():
        daily = cc[cc.FUEL_TYPE == code].set_index("DATE").RETAIL_PRICES_AVG.sort_index()
        f1 = fc[(fc.fuel == fuel) & (fc.horizon_weeks == 1)].sort_values("week_date")
        for _, r in f1.iterrows():
            t = r.week_date                                  # Friday stamp of week t
            mon_t, sun_t = t - pd.Timedelta(days=4), t + pd.Timedelta(days=2)
            mon_n = t + pd.Timedelta(days=3)                 # Monday of week t+1
            if mon_t < cc.DATE.min() or mon_n + pd.Timedelta(days=1) > last_day:
                continue
            wk = window_mean(daily, mon_t, sun_t)
            rows.append(dict(
                fuel=fuel, date=t, outcome_known=bool(r.outcome_known),
                actual=r.actual_price - r.price_now,
                production=r.pred_adl_ecm - r.price_now,
                naive=0.0,
                x2=window_mean(daily, mon_n, mon_n + pd.Timedelta(days=1)) - wk,
                x3=(window_mean(daily, mon_n, mon_n + pd.Timedelta(days=2)) - wk
                    if mon_n + pd.Timedelta(days=2) <= last_day else np.nan),
                cc_week=wk))
    res = pd.DataFrame(rows)
    res = res[res.outcome_known & res.actual.notna()].sort_values(["fuel", "date"]).reset_index(drop=True)

    # validity: ComCom's weekly mean against MBIE's weekly price, in changes
    print("ComCom weekly mean (Mon-Sun) against MBIE's adjusted_retail_price, weekly changes:")
    for fuel in FUELS:
        g = res[res.fuel == fuel]
        mbie_prev = fc[(fc.fuel == fuel) & (fc.horizon_weeks == 1)].set_index("week_date").price_now
        dm = mbie_prev.reindex(g.date).diff().to_numpy()
        dc = g.cc_week.diff().to_numpy()
        ok = np.isfinite(dm) & np.isfinite(dc)
        print(f"  {fuel:<15} r = {np.corrcoef(dm[ok], dc[ok])[0, 1]:.3f} over {ok.sum()} weeks; "
              f"slope {np.polyfit(dc[ok], dm[ok], 1)[0]:.2f}")

    # diagnostic: walk-forward combination of production's call and the 2-day reading
    res["combined"] = np.nan
    for fuel in FUELS:
        idx = res.index[res.fuel == fuel]
        for i, j in enumerate(idx):
            past = idx[:i]                        # origins before this one: outcomes known
            if len(past) < MIN_FIT:
                continue
            A = np.column_stack([np.ones(len(past)), res.loc[past, "production"], res.loc[past, "x2"]])
            b = np.linalg.lstsq(A, res.loc[past, "actual"], rcond=None)[0]
            res.loc[j, "combined"] = b[0] + b[1] * res.loc[j, "production"] + b[2] * res.loc[j, "x2"]

    methods = ["naive", "production", "x2", "x3", "combined"]
    print(f"\nMAE c/L, one week ahead; origins {res.date.min().date()} .. {res.date.max().date()}")
    print(f"  {'fuel':<15}{'n':>4}" + "".join(f"{m:>12}" for m in methods))
    for fuel in (*FUELS, "POOLED"):
        s = res if fuel == "POOLED" else res[res.fuel == fuel]
        line = f"  {fuel:<15}{len(s):>4}"
        for m in methods:
            ss = s.dropna(subset=[m])
            v = np.abs(ss[m] - ss.actual).mean()
            line += f"{v:>12.3f}" if len(ss) == len(s) else f"{v:>8.3f}({len(ss)})"
        print(line)

    s = res
    p, d = np.abs(s.production - s.actual).mean(), np.abs(s.x2 - s.actual).mean()
    gain = 1 - d / p
    print(f"\nDECISION (pre-registered): direct two-day reading at least {THRESHOLD:.0%} "
          f"below production, pooled")
    print(f"  production {p:.3f}  direct {d:.3f}  gain {gain:+.1%}  -> "
          f"{'WORTH PURSUING' if gain >= THRESHOLD else 'NOT WORTH IT'}")

    c = res.dropna(subset=["combined"])
    pc, cc_ = np.abs(c.production - c.actual).mean(), np.abs(c.combined - c.actual).mean()
    print(f"  diagnostic, combined on its {len(c)} rows: production {pc:.3f}  combined {cc_:.3f}"
          f"  gain {1 - cc_ / pc:+.1%}")
    win = (np.abs(res.x2 - res.actual) < np.abs(res.production - res.actual)).mean()
    print(f"  direct closer than production in {win:.0%} of {len(res)} calls")
    carry_horizons(fc, cc, last_day)
    return 0


def carry_horizons(fc: pd.DataFrame, cc: pd.DataFrame, last_day: pd.Timestamp) -> None:
    """Added after the first run (diagnostic): the one-week combination carried
    to h=2 and h=3 without refitting — call_h = combined_1 + (production_h -
    production_1). A separate regression per horizon was tried first and was
    worse than production (+13% at h=2, +62% at h=3): too few weeks to fit."""
    out = []
    for fuel, code in FUELS.items():
        daily = cc[cc.FUEL_TYPE == code].set_index("DATE").RETAIL_PRICES_AVG.sort_index()
        f = fc[fc.fuel == fuel].pivot_table(index="week_date", columns="horizon_weeks",
                                            values=["pred_adl_ecm", "actual_price", "price_now"])
        rows = []
        for t in f.index:
            mon_t, mon_n = t - pd.Timedelta(days=4), t + pd.Timedelta(days=3)
            if mon_t < cc.DATE.min() or mon_n + pd.Timedelta(days=1) > last_day:
                continue
            p0 = f.loc[t, ("price_now", 1)]
            rows.append(dict(
                date=t,
                x2=(window_mean(daily, mon_n, mon_n + pd.Timedelta(days=1))
                    - window_mean(daily, mon_t, t + pd.Timedelta(days=2))),
                **{f"prod{h}": f.loc[t, ("pred_adl_ecm", h)] - p0 for h in (1, 2, 3)},
                **{f"act{h}": f.loc[t, ("actual_price", h)] - p0 for h in (1, 2, 3)}))
        g = pd.DataFrame(rows).reset_index(drop=True)
        g["comb1"] = np.nan
        for i in range(len(g)):
            past = g[(g.date + pd.Timedelta(weeks=1) <= g.date[i]) & g.act1.notna()]
            if len(past) < MIN_FIT:
                continue
            A = np.column_stack([np.ones(len(past)), past.prod1, past.x2])
            b = np.linalg.lstsq(A, past.act1, rcond=None)[0]
            g.loc[i, "comb1"] = b[0] + b[1] * g.prod1[i] + b[2] * g.x2[i]
        for h in (1, 2, 3):
            s = g.dropna(subset=["comb1", f"act{h}"])
            carried = s.comb1 + (s[f"prod{h}"] - s.prod1)
            out.append(dict(fuel=fuel, h=h, n=len(s),
                            production=np.abs(s[f"prod{h}"] - s[f"act{h}"]).mean(),
                            carried=np.abs(carried - s[f"act{h}"]).mean()))
    o = pd.DataFrame(out)
    print("\nDiagnostic: the one-week combination carried to h=2, h=3, MAE c/L")
    for h in (1, 2, 3):
        q = o[o.h == h]
        for _, r in q.iterrows():
            print(f"  {r.fuel:<15} h={h} n={r.n:<3} production {r.production:7.3f}  "
                  f"carried {r.carried:7.3f}  {(r.carried / r.production - 1) * 100:+6.1f}%")
        pp = (q.production * q.n).sum() / q.n.sum()
        pc = (q.carried * q.n).sum() / q.n.sum()
        print(f"  {'POOLED':<15} h={h} n={q.n.sum():<3} production {pp:7.3f}  "
              f"carried {pc:7.3f}  {(pc / pp - 1) * 100:+6.1f}%")


if __name__ == "__main__":
    raise SystemExit(main())
