"""Does the pump price's own recent movement improve the forecast?

Production's model (`pipeline/backtest.py`) explains this week's change in the
pump price net of taxes, `d_net`, by this and the last six weeks' changes in
`importer_cost` and by last week's margin gap (the ECM term). It never looks
at how the pump price itself has been moving. Strictly that is a distributed
lag with error correction, not an ADL: an ADL also carries lags of the
dependent variable. Nothing in `docs/research.md` or `research/` has tried
them. Retail prices move in steps and with inertia, so a price already on its
way up may carry on, which the cost lags alone do not see.

THE CHANGE, AND NOTHING ELSE. p lags of `d_net` are added to production's
regression: same Final-only rows, same K = 6, same ECM term, same expanding
refit at every cutoff, same 1.15 conversion. The h-step forecast becomes
recursive: a `d_net` lag that falls inside the forecast window takes the
value predicted for that week a step earlier. Cost changes not yet observed
stay at zero, as in production.

PRE-REGISTERED, written 5 Nov 2026 before any number here was computed:

  Primary  p = 2 (`d_net` one and two weeks back).
  Against  production (p = 0), reproduced here and checked against the
           archive's `pred_adl_ecm` first.
  Sample   every origin the production backtest scores (2013 on), outcome
           known, Diesel and Regular Petrol pooled.
  PASS     pooled MAE of p = 2 lower than production at h=1 AND h=2 in
           non-crisis weeks, and not higher at h=1 or h=2 in crisis weeks.
  FAIL     anything else.

  Diagnostics, reported and not deciding: p = 1; per fuel; h=3; origins from
  1 Apr 2022 and in 2026; share of weeks in which p = 2 is closer; the AR
  coefficients at the newest cutoff.

Crisis = `crude_vol_regime == "high"`, the centred hindsight label, used only
to split results, as in `backtest.py`. Status is the current vintage, as in
production's own backtest; it affects both variants alike.

Usage:  python research/adl_ar.py [--archive-date 2026-11-05]
Reads the published archive through research/adl_decay.py. No warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "pipeline"))

import adl_decay as ad   # noqa: E402  (archive loader)

bt = ad.bt
FUELS = ("Diesel", "Regular Petrol")
PRIMARY, OTHER = 2, 1
SPLIT_2022 = pd.Timestamp("2022-04-01")


def fit(d: pd.DataFrame, upto: int, p: int) -> np.ndarray | None:
    """[const, b0..bK, g, phi_1..phi_p] from Final rows strictly before `upto`."""
    cols = ([d.d_cost.shift(i).to_numpy() for i in range(bt.K + 1)]
            + [d.dev.to_numpy()]
            + [d.d_net.shift(i).to_numpy() for i in range(1, p + 1)])
    X = np.column_stack([np.ones(len(d))] + cols)[:upto]
    y = d.d_net.to_numpy()[:upto]
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()[:upto]
    if ok.sum() < bt.MIN_TRAIN:
        return None
    return np.linalg.lstsq(X[ok], y[ok], rcond=None)[0]


def forecast(d: pd.DataFrame, t: int, beta: np.ndarray, h: int, p: int) -> float:
    """Cumulative d_net over t+1..t+h; recursive in the d_net lags."""
    dc, dn = d.d_cost.to_numpy(), d.d_net.to_numpy()
    dev = d.dev.to_numpy()[t]
    g = beta[bt.K + 2]
    phi = beta[bt.K + 3:]
    pred: dict[int, float] = {}
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(j, bt.K + 1):
            idx = t + j - k
            if idx < 0 or not np.isfinite(dc[idx]):
                return np.nan
            step += beta[1 + k] * dc[idx]
        if not np.isfinite(dev):
            return np.nan
        step += g * dev
        for i in range(1, p + 1):
            s = t + j - i
            v = dn[s] if s <= t else pred[s]
            if not np.isfinite(v):
                return np.nan
            step += phi[i - 1] * v
        pred[t + j] = step
        total += step
    return total


def mae(s: pd.DataFrame, m: str) -> float:
    return float(np.abs(s[m] - s.actual).mean())


def table(sub: pd.DataFrame, title: str) -> None:
    print(f"\n{title}\nMAE c/L on the pump price; % against production (negative = better)")
    print(f"  {'fuel':<15}{'regime':<11}{'h':>2}{'n':>5}{'production':>12}"
          f"{'p=2':>8}{'%':>7}{'p=1':>8}{'%':>7}")
    for crisis, label in ((False, "non-crisis"), (True, "crisis")):
        for h in bt.HORIZONS:
            for fuel in (*FUELS, "POOLED"):
                s = sub[(sub.hi == crisis) & (sub.h == h)]
                if fuel != "POOLED":
                    s = s[s.fuel == fuel]
                if s.empty:
                    continue
                e, a2, a1 = mae(s, "p0"), mae(s, "p2"), mae(s, "p1")
                print(f"  {fuel:<15}{label:<11}{h:>2}{len(s):>5}{e:>12.3f}"
                      f"{a2:>8.3f}{(a2 / e - 1) * 100:>6.1f}%{a1:>8.3f}{(a1 / e - 1) * 100:>6.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05")
    args = ap.parse_args()
    fc = ad.load_archive(args.archive_date)

    rows, last = [], {}
    for fuel in FUELS:
        d = bt.load(fuel)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        hi = (d.crude_vol_regime == "high").to_numpy()
        for t in range(bt.MIN_TRAIN, n):
            betas = {p: fit(d, t + 1, p) for p in (0, OTHER, PRIMARY)}
            if betas[0] is None:
                continue
            for h in bt.HORIZONS:
                r = dict(fuel=fuel, date=d.index[t], h=h, hi=bool(hi[t]), price_now=retail[t],
                         actual=retail[t + h] - retail[t] if t + h < n else np.nan)
                for p, b in betas.items():
                    f = forecast(d, t, b, h, p) if b is not None else np.nan
                    r[f"p{p}"] = f * 1.15 if np.isfinite(f) else np.nan
                rows.append(r)
            last[fuel] = betas
    res = pd.DataFrame(rows)

    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    chk = res.merge(pub[["date", "fuel", "h", "pred_adl_ecm"]], on=["date", "fuel", "h"])
    gap = (chk["price_now"] + chk["p0"] - chk["pred_adl_ecm"]).abs().max()
    print(f"PLUMBING: {len(chk)} rows, max |p=0 - published pred_adl_ecm| = {gap:.6f} c/L")
    if not gap < 0.01:
        print("  does not reproduce production; nothing below can be read", file=sys.stderr)
        return 1

    ev = res[np.isfinite(res.actual)].dropna(subset=["p0", "p1", "p2"])
    print(f"scored rows: {len(ev)}, origins {ev.date.min().date()} .. {ev.date.max().date()}")
    table(ev, "ALL ORIGINS (the decision sample)")

    print("\nDECISION (pre-registered): pooled p=2 < production at h=1 and h=2 in "
          "non-crisis weeks, and <= in crisis weeks")
    ok = []
    for crisis, strict in ((False, True), (True, False)):
        for h in (1, 2):
            s = ev[(ev.hi == crisis) & (ev.h == h)]
            e, a = mae(s, "p0"), mae(s, "p2")
            good = a < e if strict else a <= e
            ok.append(good)
            print(f"  {'crisis' if crisis else 'non-crisis':<11} h={h}: production {e:.3f}  "
                  f"p=2 {a:.3f}  -> {'yes' if good else 'NO'}")
    print(f"  => {'PASS' if all(ok) else 'FAIL'}")

    table(ev[ev.date >= SPLIT_2022], "DIAGNOSTIC - origins from 1 Apr 2022")
    table(ev[ev.date >= "2026-01-01"], "DIAGNOSTIC - origins in 2026")

    print("\nWeeks in which p=2 is closer than production:")
    for fuel in FUELS:
        for h in bt.HORIZONS:
            s = ev[(ev.fuel == fuel) & (ev.h == h)]
            win = (np.abs(s.p2 - s.actual) < np.abs(s.p0 - s.actual)).mean()
            print(f"  {fuel:<15} h={h}  {100 * win:5.1f}%  (n={len(s)})")

    print("\nAt the newest cutoff: sum b0..b6, g, phi")
    for fuel, betas in last.items():
        for p, b in betas.items():
            print(f"  {fuel:<15} p={p}  sum {b[1:bt.K + 2].sum():.3f}  g {b[bt.K + 2]:+.3f}  "
                  + "phi " + " ".join(f"{x:+.3f}" for x in b[bt.K + 3:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
