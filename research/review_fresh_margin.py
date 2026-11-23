"""The ECM term with this week's margin instead of last week's — a test with
a threshold fixed before it runs.

WHAT IS TESTED. Production's forecast takes the ECM term as `dev[t]`, the
margin of week t-1, on every step of a call made at t. The fit pairs d_net[s]
with the margin of week s-1, so for the first step the fitted pairing is the
margin of week t, which is published with week t and known at the run.
`fresh` uses it on every step. The fit is unchanged; only the forecast is.
How the week-old margin got there: docs/research.md, "What an outside review
of Report 1 asked, measured", 23 Nov 2026.

WHAT IS ALREADY KNOWN, AND WHY THIS IS NOT A CLEAN TEST. The exploratory run
of 23 Nov 2026 (research/review_m2_asym_ecm.py) has already shown the
2013-2026 aggregates: fresh better at h=2 and h=3 for all fuels (3-6%), level
for petrol at h=1 and worse for diesel at h=1 (+3.1%). A threshold set after
that cannot make those numbers a confirmation. What it does fix in advance is
everything not yet seen — the intervals, the stability across eras, and the
reading of the outcome — so that nothing can be tuned after this run. The
only clean out-of-sample test is forward, a shadow run on weeks not yet
published.

PRE-REGISTERED, 23 Nov 2026, before the first run. Nowcast path (what Report
1 plots), every call since Feb 2013 with a known outcome, Regular Petrol and
Diesel. Differences are paired, |error fresh| - |error production|, per call;
intervals are a 12-week moving-block bootstrap, 95%, 2000 resamples, seed 0.

  C1  the gain at h=2 and h=3 is real: the interval on the mean difference is
      entirely below zero at h=2 and at h=3, for both fuels.
  C2  it is not one episode: in each era — Feb 2013-Dec 2016, 2017-2020,
      2021-Oct 2026 — fresh's MAE is at most 1% above production's, at h=2
      and h=3, for both fuels (12 cells).
  C3  no proven loss at h=1, the report's one-week call: the h=1 interval is
      not entirely above zero, for either fuel.

  Ships only if C1, C2 and C3 all hold. If C1 and C2 hold and C3 fails, it
  does not ship, and the result is reported as a gain at two and three weeks
  bought with a loss at one week, for the owner to weigh. A per-horizon
  choice (fresh at h>=2 only) is a new hypothesis that this data has already
  shaped; it would need the forward test.

  Premium 95 is printed and decides nothing.

DIAGNOSTICS, deciding nothing:
  D1  where the h=1 difference sits: by quintile of |fresh dev - production
      dev|, which is the week's own margin move.
  D2  in-sample, Final rows: the regression with the margin of week s-2 added
      beside s-1. A second lag that carries weight says the correction runs
      slower than the one-week pairing assumes, which would explain h=1.

Usage:  python research/review_fresh_margin.py
Offline. Same inputs as research/wf_harness.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wf_harness as wf
from review_m2_asym_ecm import model

bt = wf.bt
DECIDE = ("Regular Petrol", "Diesel")
ERAS = (("2013-02", "2013-02-01", "2016-12-31"), ("2017-20", "2017-01-01", "2020-12-31"),
        ("2021-26", "2021-01-01", "2026-12-31"))


def paired(prod: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    m = prod.merge(fresh, on=["fuel", "date", "h"], suffixes=("_p", "_f"))
    m = m[m.outcome_known_p & (m.date >= "2013-02-01")].sort_values(["fuel", "h", "date"])
    m["ae_p"] = (m.actual_p - m.nowcast_p).abs()
    m["ae_f"] = (m.actual_p - m.nowcast_f).abs()
    m["diff"] = m.ae_f - m.ae_p
    return m


def ci(diff: pd.Series) -> tuple[float, float]:
    return wf.block_bootstrap_ci(diff.to_numpy()[:, None], lambda r: r[:, 0].mean())


def main() -> None:
    frames = wf.production_frames()
    prod = wf.walk_forward(frames)
    fresh = wf.walk_forward(frames, model("fresh", asym=False, fresh=True))
    m = paired(prod, fresh)

    print("Paired difference |err fresh| - |err production|, c/L; < 0 means fresh is better.\n")
    print(f"{'fuel':20s} {'h':>2} {'n':>4} {'MAE prod':>9} {'MAE fresh':>9} {'diff':>7} {'%':>7} {'95% CI':>18}")
    res = {}
    for (fuel, h), g in m.groupby(["fuel", "h"]):
        lo, hi = ci(g["diff"])
        res[(fuel, h)] = (lo, hi)
        print(f"{fuel:20s} {h:>2} {len(g):>4} {g.ae_p.mean():9.3f} {g.ae_f.mean():9.3f} "
              f"{g['diff'].mean():+7.3f} {g.ae_f.mean() / g.ae_p.mean() - 1:+7.1%}   [{lo:+.3f}, {hi:+.3f}]")

    print("\nBy era, MAE fresh / production - 1:")
    print(f"{'fuel':20s} {'h':>2} " + "".join(f"{e[0]:>10}" for e in ERAS))
    era = {}
    for fuel in wf.FUELS:
        for h in (1, 2, 3):
            cells = []
            for name, a, b in ERAS:
                g = m[(m.fuel == fuel) & (m.h == h) & (m.date >= a) & (m.date <= b)]
                r = g.ae_f.mean() / g.ae_p.mean() - 1
                era[(fuel, h, name)] = r
                cells.append(f"{r:+10.1%}")
            print(f"{fuel:20s} {h:>2} " + "".join(cells))

    c1 = all(res[(f, h)][1] < 0 for f in DECIDE for h in (2, 3))
    c2 = all(era[(f, h, e[0])] <= 0.01 for f in DECIDE for h in (2, 3) for e in ERAS)
    c3 = all(res[(f, 1)][0] <= 0 for f in DECIDE)
    print(f"\nC1 gain at h=2,3 below zero, both fuels:   {'PASS' if c1 else 'FAIL'}")
    print(f"C2 no era worse than +1% at h=2,3:         {'PASS' if c2 else 'FAIL'}")
    print(f"C3 no proven loss at h=1:                  {'PASS' if c3 else 'FAIL'}")
    verdict = ("SHIPS" if c1 and c2 and c3 else
               "DOES NOT SHIP: gain at h=2,3 bought with a loss at h=1" if c1 and c2 else
               "DOES NOT SHIP")
    print(f"Verdict: {verdict}")

    print("\nD1. h=1 difference by quintile of the week's own margin move |fresh dev - prod dev|, c/L:")
    for fuel in DECIDE:
        d = frames[fuel]
        mg = d.importer_margin
        x = (mg - mg.rolling(bt.ECM_WINDOW, min_periods=bt.ECM_WINDOW).mean())
        move = (x - d.dev).abs().rename("move")
        g = m[(m.fuel == fuel) & (m.h == 1)].merge(move, left_on="date", right_index=True)
        g["q"] = pd.qcut(g.move, 5, labels=[f"Q{i}" for i in range(1, 6)])
        t = g.groupby("q", observed=True).agg(move=("move", "mean"), n=("diff", "size"), diff=("diff", "mean"))
        print(f"  {fuel}: " + "  ".join(f"{q} |move| {r.move:4.1f}: {r['diff']:+.3f}" for q, r in t.iterrows()))

    print("\nD2. In-sample, Final rows 2010+: margin of week s-2 added beside s-1.")
    for fuel in DECIDE:
        d = frames[fuel]
        cols = [d.d_cost.shift(i).to_numpy() for i in range(bt.K + 1)] + [d.dev.to_numpy(), d.dev.shift(1).to_numpy()]
        X = np.column_stack([np.ones(len(d))] + cols)
        y = d.d_net.to_numpy()
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()
        b = bt.ols(y[ok], X[ok])
        rows = np.column_stack([y[ok], X[ok]])
        lo, hi = wf.block_bootstrap_ci(rows, lambda r: bt.ols(r[:, 0], r[:, 1:])[-1])
        print(f"  {fuel:15s} g(s-1) {b[-2]:+.4f}   g(s-2) {b[-1]:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")


if __name__ == "__main__":
    main()
