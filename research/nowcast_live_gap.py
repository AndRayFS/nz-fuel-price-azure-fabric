"""Yahoo's Brent at the weekly load's own moment, against the day's final price.

`docs/research.md`, 9 Nov 2026. The 8 Nov measurement in the section before it
took the bar at the CME close. The load reads Yahoo at 09:07 NZT on Thursday:
20:07 UTC in NZ summer, before the close, and 21:07 UTC in NZ winter, just
after it. This measures three things:

  1. the gap at that moment, every Wednesday Yahoo's hourly history covers;
  2. how much the gap depends on the hour it is read at - the probe's cron
     runs at 19:45 UTC and has started up to 144 minutes late;
  3. what the gap does to the forecast, in retail c/L, through the
     production code (`nowcast.nowcast_at`, `nowcast.forecast_with_nowcast`).

It is a ceiling. It assumes Yahoo's daily bar at the load still holds the last
trade; if it already holds the settlement, the gap is zero. The probe step in
weekly.yml answers which.

Method. The price "as of" T is the close of the last hourly `BZ=F` bar of that
trading session (18:00 ET the day before to 17:00 ET) that ended at or before
T; the final is Yahoo's daily close for the session, the settlement. Left out,
as on 8 Nov: the ten trading days before each expiry, where the hourly series
is already on the next contract and the gap is the spread (kept, they show a
bias of -0.3 to -0.4%), and any day whose settlement lies outside the
session's hourly range. The load reads the front contract by its own symbol,
so neither applies to it.

Yahoo serves hourly bars for its last 730 days only: a rerun on a later date
measures a different two years. `--save DIR` keeps the three raw answers,
`--raw DIR` reads them back instead of asking Yahoo. Part 3 needs the local
`data/panel_weekly.csv` and `data/period_flags.csv` (`task panel`, `task flags`)
and two more requests, for the full daily history.

Usage:  python research/nowcast_live_gap.py [--save DIR | --raw DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import backtest as bt                      # noqa: E402
import nowcast as nc                       # noqa: E402

ET, NZ = "America/New_York", "Pacific/Auckland"
CRISIS = pd.Timestamp("2026-02-28")        # 06_iranus_2026 in seeds/periods.csv
NEAR_EXPIRY = 10                           # trading days, as on 8 Nov
READINGS = ("19:45", "20:07", "21:07", "21:45", "22:09")   # UTC
FILES = ("bz_60m.json", "bz_1d.json", "fx_1d.json")


def fetch(save: Path | None) -> dict[str, bytes]:
    now = int(time.time())
    p1 = now - 728 * 86400
    base = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p}&period2={n}&interval={i}"
    urls = dict(zip(FILES, (base.format(s="BZ=F", p=p1, n=now, i="60m"),
                            base.format(s="BZ=F", p=p1 - 20 * 86400, n=now, i="1d"),
                            base.format(s="NZDUSD=X", p=p1 - 20 * 86400, n=now, i="1d"))))
    out = {}
    for name, url in urls.items():
        req = urllib.request.Request(url, headers=nc.HEADERS)
        with urllib.request.urlopen(req, timeout=nc.TIMEOUT) as r:
            out[name] = r.read()
        if save:
            save.mkdir(parents=True, exist_ok=True)
            (save / name).write_bytes(out[name])
        time.sleep(1)
    return out


def bars(body: bytes) -> pd.DataFrame:
    r = json.loads(body)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    t = pd.to_datetime(r["timestamp"], unit="s", utc=True)
    return pd.DataFrame({"h": q["high"], "l": q["low"], "c": q["close"]}, index=t).dropna()


def stats(v: pd.Series) -> pd.Series:
    a = v.abs()
    return pd.Series(dict(n=len(v), median=a.median(), p90=a.quantile(.9),
                          p95=a.quantile(.95), max=a.max(), bias=v.mean()))


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--save", type=Path)
    g.add_argument("--raw", type=Path)
    args = ap.parse_args()
    raw = ({n: (args.raw / n).read_bytes() for n in FILES} if args.raw else fetch(args.save))

    h = bars(raw["bz_60m.json"])
    h = h[h.index.minute == 0]
    dd, fxd = bars(raw["bz_1d.json"]), bars(raw["fx_1d.json"])
    last_hour = h.index.max()
    settle = pd.Series(dd.c.values, index=dd.index.tz_convert(ET).normalize().tz_localize(None))
    settle = settle[settle.index < last_hour.tz_convert(ET).normalize().tz_localize(None)]
    fx = pd.Series(fxd.c.values, index=fxd.index.tz_convert("UTC").normalize().tz_localize(None))

    def session(D):
        s = (D - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).tz_localize(ET)
        e = (D + pd.Timedelta(hours=17)).tz_localize(ET)
        return h[(h.index >= s) & (h.index < e)]

    def asof(sb, T):
        ok = sb[sb.index + pd.Timedelta(hours=1) <= T]
        return ok.c.iloc[-1] if len(ok) else np.nan

    def to_expiry(D):
        y, m = nc.contract_on(D.date())
        return int(np.busday_count(D.date(), nc.expiry(y, m)))

    rows = []
    for D, fin in settle.items():
        if D.dayofweek > 4:
            continue
        sb = session(D)
        if len(sb) < 10:
            continue
        rec = dict(D=D, fin=fin, us_dst=bool(D.tz_localize(ET).dst()),
                   keep=(sb.l.min() - 0.005 <= fin <= sb.h.max() + 0.005) and to_expiry(D) > NEAR_EXPIRY)
        if D.dayofweek == 2:
            load = (D + pd.Timedelta(days=1, hours=9, minutes=7)).tz_localize(NZ).tz_convert("UTC")
            rec["load_utc"], rec["at_load"] = load.strftime("%H:%M"), asof(sb, load)
        for lab in READINGS:
            rec["at_" + lab] = asof(sb, pd.Timestamp(f"{D.date()} {lab}", tz="UTC"))
        rows.append(rec)
    R = pd.DataFrame(rows)

    W = R[(R.D.dt.dayofweek == 2) & R.keep].copy()
    W["gap_pct"] = 100 * (W.at_load / W.fin - 1)
    # A wrong Wednesday moves the 3-day mean of the feature by a third of it.
    W["gap_x_cpl"] = [(a - f) / fx.asof(D) / 158.987 * 100 / 3 for a, f, D in zip(W.at_load, W.fin, W.D)]
    print(f"Hourly BZ=F {h.index.min():%d %b %Y} - {last_hour:%d %b %Y}; "
          f"Wednesdays kept {len(W)} of {int((R.D.dt.dayofweek == 2).sum())}; "
          f"exact zeros {int((W.at_load == W.fin).sum())}, under 0.1% {int((W.gap_pct.abs() < 0.1).sum())}")

    groups = {"all": W,
              "NZ summer, load 20:07 UTC": W[W.load_utc == "20:07"],
              "NZ winter, load 21:07 UTC": W[W.load_utc == "21:07"],
              "calm, before 28 Feb 2026": W[W.D < CRISIS],
              "crisis, from 28 Feb 2026": W[W.D >= CRISIS]}
    print("\n1. Wednesday at the load's moment against the day's final, % of Brent")
    print(pd.DataFrame({k: stats(v.gap_pct) for k, v in groups.items()}).T.round(3).to_string())
    print("\n   the same on the feature's 3-day mean, NZ c/L")
    print(pd.DataFrame({k: stats(v.gap_x_cpl) for k, v in groups.items()}).T.round(3).to_string())

    E = R[R.keep & ~R.us_dst]
    print("\n2. By the hour it is read: every weekday in US winter (the probe's season), % of Brent")
    print(pd.DataFrame({lab + " UTC": stats((100 * (E["at_" + lab] / E.fin - 1)).dropna())
                        for lab in READINGS}).T.round(3).to_string())

    bz = nc.daily(nc.parse_chart(nc.get(nc.chart_url("BZ=F", "1d", nc.HISTORY_FROM))))
    fxl = nc.daily(nc.parse_chart(nc.get(nc.chart_url("NZDUSD=X", "1d", nc.HISTORY_FROM))))
    cpl = nc.brent_nzd_cpl(bz, fxl)
    out = []
    for fuel in ("Regular Petrol", "Premium Petrol 95R", "Diesel"):
        d = bt.load(fuel)
        stamps = d.index.append(pd.DatetimeIndex([d.index[-1] + pd.Timedelta(days=7)]))
        x3 = nc.features(cpl, stamps)["x3"].to_numpy()
        d_cost, is_final = d.d_cost.to_numpy(), d.is_final.to_numpy()
        pos = {s: i for i, s in enumerate(stamps)}
        for _, w in W.iterrows():
            k = pos.get(w.D + pd.Timedelta(days=2))        # the Friday stamping the week
            if k is None or k < 1 or not np.isfinite(x3[k]):
                continue
            t = k - 1
            b = bt.fit_adl(d, t + 1, with_ecm=True)
            if b is None:
                continue
            base = nc.nowcast_at(x3, d_cost, is_final, t)
            xp = x3.copy()
            xp[k] += 1.0
            bump = nc.nowcast_at(xp, d_cost, is_final, t)
            for hz in (1, 2, 3):
                s = 1.15 * (nc.forecast_with_nowcast(d, t, b, hz, True, bump)
                            - nc.forecast_with_nowcast(d, t, b, hz, True, base))
                out.append(dict(fuel=fuel, h=hz, sens=s, effect=s * w.gap_x_cpl))
    O = pd.DataFrame(out)
    print("\n3. On the forecast, retail c/L (sens: c/L of forecast per 1 c/L of the feature)")
    print(O.groupby(["fuel", "h"]).agg(
        n=("effect", "size"), sens=("sens", "median"),
        median=("effect", lambda v: v.abs().median()),
        p95=("effect", lambda v: v.abs().quantile(.95)),
        max=("effect", lambda v: v.abs().max())).round(3).to_string())


if __name__ == "__main__":
    main()
