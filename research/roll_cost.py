"""Is the futures roll a real move in MBIE's cost, or a phantom? 7 Nov 2026.

research/roll_weeks.py found the nowcast does *better* in weeks where a Brent
contract expires inside its window, although there the daily BZ=F series
jumps by the gap between two contracts. One explanation: MBIE's importer cost
moves the same way at the turn of the month, so the jump is signal. Against
it, docs/mbie_notes.md: the cost is "this week's Singapore spot" product
quote, with no month in it.

Test. For each origin week t (MBIE's Friday stamp), over the nowcast's window
(Mon-Wed of week t+1 against Mon-Fri of week t):
  spot  = change in FRED Dated Brent (no contracts, no roll)
  basis = change in Yahoo BZ=F minus spot; in roll weeks it carries the jump
  y     = MBIE importer cost, week t+1 minus week t, c/L, per fuel
Fit y = fuel intercepts + b_spot * spot + b_basis * basis, three fuels
pooled, separately on roll and non-roll weeks. Moving-block bootstrap over
origin dates (blocks of 8), 2,000 resamples, 90% CI.

Sample: origins from March 2016 only, where research/roll_weeks.py's D0 check
confirmed the expiry calendar (2013-15 labels were not trusted); FRED's
cached series ends 15 Sep 2026.

RULE, written before the run (roll weeks):
  real      b_basis CI lower end > 0 and b_basis / b_spot >= 0.5
  phantom   b_basis CI includes 0, or b_basis / b_spot < 0.25
  partial   anything else
Non-roll weeks are reported, not judged.

PREDICTION, written before the run: phantom. MBIE's cost is a weekly
Singapore spot product quote with no contract month, so a jump that exists
only because a futures contract expired should not reach it. If so, the
nowcast's better record in roll weeks needs another explanation.

    python research/roll_cost.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "research"))

import roll_weeks as rw                            # noqa: E402
from nowcast_brent import week_means               # noqa: E402

PANEL = ROOT / "data" / "nowcast_backwardation" / "panel_weekly.csv"   # archive 2026-11-05
FUELS = ("Diesel", "Regular Petrol", "Premium Petrol 95R")
FROM, TO = pd.Timestamp("2016-03-01"), pd.Timestamp("2026-09-04")
REPS, SEED, BLOCK = 2000, 20261107, 8


def feature(daily: pd.Series, stamps: pd.DatetimeIndex) -> pd.Series:
    m = week_means(daily, stamps)
    return pd.Series((m.m3.shift(-1) - m.m5).to_numpy(), index=stamps)   # at origin t


def frame() -> pd.DataFrame:
    p = pd.read_csv(PANEL, parse_dates=["Date"])
    yh = pd.read_csv(rw.YAHOO, parse_dates=["date"]).set_index("date").close
    fr = pd.to_numeric(pd.read_csv(rw.FRED, parse_dates=["date"]).set_index("date").brent_usd_bbl,
                       errors="coerce").dropna()
    rows = []
    for fuel in FUELS:
        d = p[p.Fuel == fuel].set_index("Date").sort_index()
        stamps = pd.DatetimeIndex(d.index)
        spot = feature(fr, stamps)
        fut = feature(yh, stamps)
        y = d.importer_cost.shift(-1) - d.importer_cost
        nxt = pd.Series(stamps, index=stamps).shift(-1)
        rows.append(pd.DataFrame({"fuel": fuel, "date": stamps, "y": y.to_numpy(),
                                  "spot": spot.to_numpy(), "basis": (fut - spot).to_numpy(),
                                  "gap_days": (nxt - stamps).dt.days.to_numpy()}))
    f = pd.concat(rows, ignore_index=True)
    f = f[(f.date >= FROM) & (f.date <= TO) & (f.gap_days == 7)].dropna()
    f["roll"] = rw.label(f.date).to_numpy()
    return f


def fit(f: pd.DataFrame) -> np.ndarray:
    X = np.column_stack([(f.fuel == x).to_numpy(float) for x in FUELS] + [f.spot, f.basis])
    return np.linalg.lstsq(X, f.y.to_numpy(), rcond=None)[0][-2:]     # b_spot, b_basis


def boot(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    dates = np.sort(f.date.unique())
    by = {d: g for d, g in f.groupby("date")}
    n = len(dates)
    rng = np.random.default_rng(SEED)
    k = int(np.ceil(n / BLOCK))
    out = []
    for _ in range(REPS):
        starts = rng.integers(0, n - BLOCK + 1, size=k)
        pick = np.concatenate([dates[s:s + BLOCK] for s in starts])[:n]
        out.append(fit(pd.concat([by[d] for d in pick], ignore_index=True)))
    out = np.array(out)
    return fit(f), out


def main() -> int:
    f = frame()
    print(f"origins {f.date.nunique()} ({f.date.min().date()}..{f.date.max().date()}), "
          f"roll weeks {f[f.roll].date.nunique()}\n")
    verdicts = {}
    for name, sub in (("roll", f[f.roll]), ("non-roll", f[~f.roll])):
        (bs, bb), draws = boot(sub)
        lo, hi = np.quantile(draws, [0.05, 0.95], axis=0)
        ratio = bb / bs
        rlo, rhi = np.quantile(draws[:, 1] / draws[:, 0], [0.05, 0.95])
        v = ("real" if lo[1] > 0 and ratio >= 0.5 else
             "phantom" if (lo[1] <= 0 <= hi[1]) or ratio < 0.25 else "partial")
        verdicts[name] = v
        print(f"{name:9s} n={len(sub):4d}  b_spot {bs:6.3f} [{lo[0]:6.3f}, {hi[0]:6.3f}]  "
              f"b_basis {bb:6.3f} [{lo[1]:6.3f}, {hi[1]:6.3f}]  "
              f"ratio {ratio:5.2f} [{rlo:5.2f}, {rhi:5.2f}]  -> {v}")
        for fuel in FUELS:
            s = sub[sub.fuel == fuel]
            X = np.column_stack([np.ones(len(s)), s.spot, s.basis])
            b = np.linalg.lstsq(X, s.y.to_numpy(), rcond=None)[0]
            print(f"    {fuel:20s} b_spot {b[1]:6.3f}  b_basis {b[2]:6.3f}")
    print(f"\nRULE (roll weeks): {verdicts['roll']}.  PREDICTION was: phantom -> "
          f"{'held' if verdicts['roll'] == 'phantom' else 'MISSED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
