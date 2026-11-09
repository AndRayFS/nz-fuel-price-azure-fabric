"""Does MBIE's importer cost see the roll step itself? 10 Nov 2026.

research/roll_cost.py (7 Nov) split the futures move into a FRED-spot part and
a basis part and found the basis passes to MBIE's cost in roll weeks at 0.73 of
a spot move. Argus's methodology (Oct 2026) gives the Singapore quote MBIE uses
a rolling window, "loading 15-30 days forward", with no month to switch
(docs/mbie_notes.md), so the step has no mechanism. This check needs no FRED:
it splits the calendar-front feature itself into a same-contract move and the
step.

For each origin t, over the nowcast's window (mean Mon-Wed t+1 minus mean
Mon-Fri t, research/nowcast_brent.week_means):
  front = the feature on Yahoo's daily BZ=F (calendar front, switches after
          expiry E; what the backtest uses)
  same  = the feature on one contract, the one that is front after E, every
          day of the window. Before E its price is taken from Yahoo's hourly
          BZ=F, which is already on that contract 4-9 trading days before E:
          the hourly bar 19:00-20:00 London, midpoint of open and close, as a
          proxy for the 19:30 settlement.
  step  = front - same; zero outside roll weeks
  y     = MBIE importer cost, week t+1 minus week t, c/L
Fit y = fuel intercepts + b_same * same + b_step * step, three fuels pooled,
roll weeks (research/roll_weeks.label). Bootstrap over origin dates, 2,000
resamples, 90% CI. Non-roll weeks over the same span give b_same alone.

Days before E on which the hourly series is not yet on the new contract
(|hourly - daily| closer to 0 than to the spread on E) take the spread of the
nearest switched day. Roll origins whose window holds an expiry with no hourly
bar on the day itself (Thanksgiving Friday, 30 Jan 2026) or before the hourly
span are left out: their step would be zero by construction.

RULE, written before the run (roll weeks), as in roll_cost.py:
  real      b_step CI lower end > 0 and b_step / b_same >= 0.5
  phantom   b_step CI includes 0, or b_step / b_same < 0.25
  partial   anything else

PREDICTION, written before the run: real, b_step / b_same near 0.7, as on
7 Nov. The sample is two years instead of ten, so the CI will be wide.

Run first on 10 Nov 2026 as a scratch check, with the rule and prediction
above already written; committed the same day. That first run kept the three
origins now left out, and gave a ratio of 1.09 instead of 1.12.

Yahoo serves hourly bars for its last 730 days only: a rerun on a later date
measures a different two years. `--save DIR` keeps the two raw answers,
`--raw DIR` reads them back instead of asking Yahoo; the 10 Nov answers are in
`data/roll_same_contract/`. The panel is the 5 Nov archive, as in roll_cost.py.

    python research/roll_same_contract.py [--save DIR | --raw DIR]
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
sys.path.insert(0, str(ROOT / "research"))

import nowcast as nc                          # noqa: E402
import roll_weeks as rw                       # noqa: E402
from nowcast_brent import week_means          # noqa: E402

PANEL = ROOT / "data" / "nowcast_backwardation" / "panel_weekly.csv"   # archive 2026-11-05
FUELS = ("Diesel", "Regular Petrol", "Premium Petrol 95R")
FILES = ("bz_60m.json", "bz_1d.json")
CRISIS = pd.Timestamp("2026-02-28")           # 06_iranus_2026 in seeds/periods.csv
REPS, SEED = 2000, 20261110


def fetch(save: Path | None) -> dict[str, bytes]:
    now = int(time.time())
    p1 = now - 728 * 86400
    base = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?period1={p}&period2={n}&interval={i}"
    out = {}
    for name, p, i in (("bz_60m.json", p1, "60m"), ("bz_1d.json", p1 - 20 * 86400, "1d")):
        req = urllib.request.Request(base.format(p=p, n=now, i=i), headers=nc.HEADERS)
        with urllib.request.urlopen(req, timeout=nc.TIMEOUT) as r:
            out[name] = r.read()
        if save:
            save.mkdir(parents=True, exist_ok=True)
            (save / name).write_bytes(out[name])
        time.sleep(1)
    return out


def load(raw: dict[str, bytes]) -> tuple[pd.Series, pd.Series]:
    """Daily closes, and the hourly settlement proxy, both by New York trading date."""
    d = json.loads(raw["bz_1d.json"])["chart"]["result"][0]
    daily = pd.Series(d["indicators"]["quote"][0]["close"],
                      index=pd.to_datetime(d["timestamp"], unit="s", utc=True)
                      .tz_convert("America/New_York").tz_localize(None).normalize()).dropna()
    daily = daily[~daily.index.duplicated(keep="last")]
    h = json.loads(raw["bz_60m.json"])["chart"]["result"][0]
    q = h["indicators"]["quote"][0]
    t = pd.to_datetime(h["timestamp"], unit="s", utc=True)
    bars = pd.DataFrame({"o": q["open"], "c": q["close"]}, index=t).dropna()
    pick = bars[bars.index.tz_convert("Europe/London").hour == 19]   # holds 19:30 London
    proxy = pd.Series(((pick.o + pick.c) / 2).to_numpy(),
                      index=pick.index.tz_convert("UTC").tz_localize(None).normalize())
    return daily, proxy[~proxy.index.duplicated(keep="last")]


def spreads(daily: pd.Series, proxy: pd.Series) -> tuple[pd.Series, pd.DataFrame]:
    """old - new on each day up to and including each expiry inside the hourly span."""
    s, log = {}, []
    days = daily.index
    for e in rw.EXPIRIES:
        e = pd.Timestamp(e)
        if e < proxy.index.min() + pd.Timedelta(days=20) or e > days.max():
            continue
        if e not in daily.index or e not in proxy.index:
            log.append(dict(expiry=e.date(), note="no bar on expiry day"))
            continue
        pre = days[days <= e][-12:]
        diff = daily.reindex(pre) - proxy.reindex(pre)            # old - new where switched
        se = diff.loc[e]
        on_new = (diff - se).abs() < diff.abs()
        switched = [d for d in pre if bool(on_new.get(d, False)) and not np.isnan(diff[d])]
        first = min(switched) if switched else e
        for d in pre:
            if d in switched:
                s[d] = diff[d]
            elif d >= first:
                s[d] = se
            else:
                s[d] = diff[first] if not np.isnan(diff[first]) else se
        log.append(dict(expiry=e.date(), spread_on_expiry=round(se, 2),
                        hourly_switched_days_before=int((pre < e).sum() - (pre < first).sum())))
    return pd.Series(s).sort_index(), pd.DataFrame(log)


def frame(daily: pd.Series, s: pd.Series, start: pd.Timestamp, have: set) -> pd.DataFrame:
    p = pd.read_csv(PANEL, parse_dates=["Date"])
    same_px = daily - s.reindex(daily.index).fillna(0.0)
    rows = []
    for fuel in FUELS:
        d = p[p.Fuel == fuel].set_index("Date").sort_index()
        stamps = pd.DatetimeIndex(d.index)
        mf, ms = week_means(daily, stamps), week_means(same_px, stamps)
        nxt = pd.Series(stamps, index=stamps).shift(-1)
        rows.append(pd.DataFrame({
            "fuel": fuel, "date": stamps,
            "y": (d.importer_cost.shift(-1) - d.importer_cost).to_numpy(),
            "front": (mf.m3.shift(-1) - mf.m5).to_numpy(),
            "same": (ms.m3.shift(-1) - ms.m5).to_numpy(),
            "gap_days": (nxt - stamps).dt.days.to_numpy()}))
    f = pd.concat(rows, ignore_index=True)
    f["step"] = f.front - f.same
    f = f[(f.date >= start) & (f.gap_days == 7)].dropna()
    f["roll"] = rw.label(f.date).to_numpy()

    def expiries(d):
        mon, wed = d - pd.Timedelta(days=4), d + pd.Timedelta(days=5)
        return [pd.Timestamp(e) for e in rw.EXPIRIES if mon <= pd.Timestamp(e) < wed]

    f["bad"] = [any(e not in have for e in expiries(d)) for d in f.date]
    f["quarter"] = [any(e.month in (3, 6, 9, 12) for e in expiries(d)) for d in f.date]
    return f


def fit(f: pd.DataFrame, cols: list[str]) -> np.ndarray:
    X = np.column_stack([(f.fuel == x).to_numpy(float) for x in FUELS] + [f[c] for c in cols])
    return np.linalg.lstsq(X, f.y.to_numpy(), rcond=None)[0][-len(cols):]


def boot(f: pd.DataFrame, cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    dates = np.sort(f.date.unique())
    by = {d: g for d, g in f.groupby("date")}
    rng = np.random.default_rng(SEED)
    out = [fit(pd.concat([by[d] for d in rng.choice(dates, len(dates))], ignore_index=True), cols)
           for _ in range(REPS)]
    return fit(f, cols), np.array(out)


def mae(f: pd.DataFrame, col: str) -> float:
    X = np.column_stack([(f.fuel == x).to_numpy(float) for x in FUELS] + [f[col]])
    b = np.linalg.lstsq(X, f.y.to_numpy(), rcond=None)[0]
    return float(np.abs(f.y.to_numpy() - X @ b).mean())


def show(name: str, x: pd.DataFrame) -> tuple[float, float, float, float]:
    (bs, bj), dr = boot(x, ["same", "step"])
    lo, hi = np.percentile(dr, [5, 95], axis=0)
    rr = np.percentile(dr[:, 1] / dr[:, 0], [5, 95])
    print(f"{name:42s} n={x.date.nunique():2d}  b_same {bs:5.2f} [{lo[0]:5.2f},{hi[0]:5.2f}]  "
          f"b_step {bj:5.2f} [{lo[1]:5.2f},{hi[1]:5.2f}]  ratio {bj / bs:5.2f} [{rr[0]:5.2f},{rr[1]:5.2f}]  "
          f"MAE front {mae(x, 'front'):.2f} same {mae(x, 'same'):.2f}")
    return bs, bj, lo[1], hi[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--save", type=Path)
    g.add_argument("--raw", type=Path)
    args = ap.parse_args()
    raw = ({n: (args.raw / n).read_bytes() for n in FILES} if args.raw else fetch(args.save))
    daily, proxy = load(raw)

    near = set()
    for e in rw.EXPIRIES:
        near |= set(daily.index[daily.index <= pd.Timestamp(e)][-12:])
    common = [d for d in proxy.index if d in daily.index and d not in near]
    err = (proxy.reindex(common) - daily.reindex(common)).abs()
    print(f"hourly {proxy.index.min().date()}..{proxy.index.max().date()}, daily to {daily.index.max().date()}")
    print(f"settlement proxy vs daily close, away from expiries: n={len(err)}, "
          f"median {err.median():.2f}, p90 {err.quantile(.9):.2f} USD\n")

    s, log = spreads(daily, proxy)
    print(log.to_string(index=False), "\n")
    have = set(pd.to_datetime(log.dropna(subset=["spread_on_expiry"]).expiry))
    start = proxy.index.min() + pd.Timedelta(days=14)
    f = frame(daily, s, start, have)
    print("left out, no spread for an expiry in the window:",
          [d.date() for d in sorted(f[f.roll & f.bad].date.unique())])
    r, n = f[f.roll & ~f.bad], f[~f.roll]
    one = r.drop_duplicates("date")
    print(f"origins {f.date.nunique()} ({f.date.min().date()}..{f.date.max().date()}), roll weeks "
          f"{r.date.nunique()}; |step| median {one.step.abs().median():.2f}, max {one.step.abs().max():.2f} USD\n")

    bs, bj, lo, hi = show("roll weeks", r)
    (bn,), dn = boot(n, ["same"])
    print(f"{'non-roll weeks':42s} n={n.date.nunique():2d}  b_same {bn:5.2f} "
          f"[{np.percentile(dn[:, 0], 5):5.2f},{np.percentile(dn[:, 0], 95):5.2f}]")
    if lo > 0 and bj / bs >= 0.5:
        v = "real"
    elif lo <= 0 <= hi or bj / bs < 0.25:
        v = "phantom"
    else:
        v = "partial"
    print(f"RULE -> {v}   (prediction: real)\n")

    print("Robustness, not judged:")
    se = log.dropna(subset=["spread_on_expiry"])
    s2 = {}
    for e, v_ in zip(pd.to_datetime(se.expiry), se.spread_on_expiry):
        for d in daily.index[daily.index <= e][-12:]:
            s2[d] = v_
    f2 = frame(daily, pd.Series(s2).sort_index(), start, have)
    show("one spread per expiry (the expiry day's)", f2[f2.roll & ~f2.bad])
    show("before the crisis", r[r.date < CRISIS])
    show("crisis only", r[r.date >= CRISIS])
    show("without 3 Apr and 1 May 2026", r[~r.date.isin(pd.to_datetime(["2026-04-03", "2026-05-01"]))])
    show("quarter turns only", r[r.quarter])
    show("other month turns", r[~r.quarter])
    loo = sorted(fit(r[r.date != d], ["same", "step"])[1] for d in r.date.unique())
    print(f"leave one origin out: b_step {loo[0]:.2f} .. {loo[-1]:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
