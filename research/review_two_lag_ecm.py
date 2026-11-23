"""An ECM with two margin lags, in the fit and in the forecast — a test with
a threshold fixed before it runs.

WHY. The fresh-margin test (research/review_fresh_margin.py, 23 Nov 2026)
did not ship, and its diagnostic D2 said why: in-sample, with the margins of
weeks s-1 and s-2 side by side, the correction is carried by s-2 (petrol
-0.26, diesel -0.39) and s-1 enters with the opposite sign (+0.12, +0.20).
Production's single term is fitted on s-1 but forecast with t-1, which at
h=1 happens to be the s-2 the data prefers, and at h=2-3 is a week too old.
This specification states both lags, so each step can be given the margins
the fit was given:

    fit       d_net[s] = a + sum_k b_k d_cost[s-k] + g1 * x[s-1] + g2 * x[s-2]
    forecast  step j of a call at t uses x[t+j-1] and x[t+j-2]

`x[w]` is the deviation of week w's margin from its trailing 104-week mean,
production's `dev` one week on. At the run, x is known up to x[t]. ONE RULE
for the rest, the one production already applies to its single term: an
unknown future deviation is held at x[t]. So
    j=1   g1 * x[t]   + g2 * x[t-1]     both known: the fitted pairing
    j=2   g1 * x[t]*  + g2 * x[t]       * held
    j=3   g1 * x[t]*  + g2 * x[t]*
A projected margin path (next week's margin from the call itself) is the
obvious alternative and is NOT run here: one rule, chosen before the result.

WHAT SHAPED THIS. D2 was measured on the full sample, so the specification
was chosen with hindsight, as K=6 was. The walk-forward refits at every
cutoff on the past only, but it cannot undo the choice. The clean test is
forward, on weeks not yet published.

PRE-REGISTERED, 23 Nov 2026, before the first run. Against production
(single term, x[t-1] on every step). Nowcast path, every call since Feb 2013
with a known outcome; Regular Petrol and Diesel decide. Paired differences
|error two-lag| - |error production| per call; 12-week moving-block
bootstrap, 95%, 2000 resamples, seed 0. Eras Feb 2013-Dec 2016, 2017-2020,
2021-Oct 2026.

  C1  gain at h=2 and h=3: the interval entirely below zero at both, for both
      fuels.
  C2  no era worse than +1% in MAE, at ANY horizon h=1, 2, 3, for both fuels
      (18 cells). Stricter than the fresh test, which checked h=2-3 only:
      the point of two lags is to keep h=1.
  C3  no proven loss at h=1: the interval not entirely above zero, both fuels.

  Ships only if C1, C2 and C3 all hold. Premium 95 and the fresh variant are
  printed beside and decide nothing.

DIAGNOSTICS, deciding nothing: g1 and g2 at the last cutoff; the h=1
difference by quintile of the week's own margin move, as D1 of the fresh
test; the calls from the newest week of the panel under each variant.

Usage:  python research/review_two_lag_ecm.py
Offline. Same inputs as research/wf_harness.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wf_harness as wf
from review_m2_asym_ecm import model as m2_model

bt = wf.bt
DECIDE = ("Regular Petrol", "Diesel")
ERAS = (("2013-16", "2013-02-01", "2016-12-31"), ("2017-20", "2017-01-01", "2020-12-31"),
        ("2021-26", "2021-01-01", "2026-12-31"))


def own_dev(d: pd.DataFrame) -> np.ndarray:
    """x[w]: week w's own margin against the trailing 104-week mean that
    includes it. Production's dev[w] is x[w-1]."""
    m = d.importer_margin
    return (m - m.rolling(bt.ECM_WINDOW, min_periods=bt.ECM_WINDOW).mean()).to_numpy()


def forecast(d, t, beta, h, ncv, ecm) -> float:
    """bt.adl_forecast / nowcast.forecast_with_nowcast with the ECM term of
    step j given by ecm(beta, t, j)."""
    dc = d.d_cost.to_numpy()
    use_nc = np.isfinite(ncv)
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(max(0, j - 1) if use_nc else j, bt.K + 1):
            idx = t + j - k
            val = ncv if (use_nc and idx == t + 1) else (dc[idx] if idx <= t else np.nan)
            if idx < 0 or not np.isfinite(val):
                return np.nan
            step += beta[1 + k] * val
        e = ecm(beta, t, j)
        if not np.isfinite(e):
            return np.nan
        total += step + e
    return total


def two_lag_model() -> wf.Model:
    cache: dict = {}

    def x_of(d):
        if id(d) not in cache:
            cache[id(d)] = own_dev(d)
        return cache[id(d)]

    def fit(d, upto):
        cols = [d.d_cost.shift(i).to_numpy() for i in range(bt.K + 1)]
        cols += [d.dev.to_numpy(), d.dev.shift(1).to_numpy()]     # x[s-1], x[s-2]
        X = np.column_stack([np.ones(len(d))] + cols)[:upto]
        y = d.d_net.to_numpy()[:upto]
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()[:upto]
        return bt.ols(y[ok], X[ok]) if ok.sum() >= bt.MIN_TRAIN else None

    def fcst(d, t, beta, h, ncv):
        x = x_of(d)
        known = lambda w: x[min(w, t)]          # the one rule: hold at x[t]
        return forecast(d, t, beta, h, ncv,
                        lambda b, tt, j: b[-2] * known(tt + j - 1) + b[-1] * known(tt + j - 2))

    return wf.Model("two_lag", fit, fcst)


def plumbing(frames: dict) -> None:
    """The generic forecast with production's term is production."""
    def fcst(d, t, beta, h, ncv):
        dev = d.dev.to_numpy()
        return forecast(d, t, beta, h, ncv, lambda b, tt, j: b[-1] * dev[tt])
    a = wf.walk_forward(frames, wf.Model("generic", wf.PRODUCTION.fit, fcst))
    b = wf.walk_forward(frames)
    gap = (a.nowcast - b.nowcast).abs().max()
    assert gap < 1e-9, gap
    for d in frames.values():
        both = pd.concat([pd.Series(own_dev(d), index=d.index), d.dev.shift(-1)], axis=1).dropna()
        assert (both.iloc[:, 0] - both.iloc[:, 1]).abs().max() < 1e-9
    print(f"plumbing: generic forecast = production to {gap:.1e}; x[w] = dev[w+1]\n")


def paired(base: pd.DataFrame, alt: pd.DataFrame) -> pd.DataFrame:
    m = base.merge(alt, on=["fuel", "date", "h"], suffixes=("_p", "_a"))
    m = m[m.outcome_known_p & (m.date >= "2013-02-01")].sort_values(["fuel", "h", "date"])
    m["ae_p"] = (m.actual_p - m.nowcast_p).abs()
    m["ae_a"] = (m.actual_p - m.nowcast_a).abs()
    m["diff"] = m.ae_a - m.ae_p
    return m


def main() -> None:
    frames = wf.production_frames()
    plumbing(frames)
    prod = wf.walk_forward(frames)
    two = wf.walk_forward(frames, two_lag_model())
    fresh = wf.walk_forward(frames, m2_model("fresh", asym=False, fresh=True))
    m = paired(prod, two)
    mf = paired(prod, fresh)

    print("Paired difference |err two-lag| - |err production|, c/L; < 0 means two-lag is better.")
    print(f"{'fuel':20s} {'h':>2} {'n':>4} {'MAE prod':>9} {'two-lag':>8} {'diff':>7} {'%':>7} "
          f"{'95% CI':>18} | {'fresh %':>8}")
    res = {}
    for (fuel, h), g in m.groupby(["fuel", "h"]):
        lo, hi = wf.block_bootstrap_ci(g["diff"].to_numpy()[:, None], lambda r: r[:, 0].mean())
        res[(fuel, h)] = (lo, hi)
        gf = mf[(mf.fuel == fuel) & (mf.h == h)]
        print(f"{fuel:20s} {h:>2} {len(g):>4} {g.ae_p.mean():9.3f} {g.ae_a.mean():8.3f} "
              f"{g['diff'].mean():+7.3f} {g.ae_a.mean() / g.ae_p.mean() - 1:+7.1%}   [{lo:+.3f}, {hi:+.3f}] | "
              f"{gf.ae_a.mean() / gf.ae_p.mean() - 1:+8.1%}")

    print("\nBy era, MAE two-lag / production - 1:")
    print(f"{'fuel':20s} {'h':>2} " + "".join(f"{e[0]:>10}" for e in ERAS))
    era = {}
    for fuel in wf.FUELS:
        for h in (1, 2, 3):
            cells = []
            for name, a, b in ERAS:
                g = m[(m.fuel == fuel) & (m.h == h) & (m.date >= a) & (m.date <= b)]
                era[(fuel, h, name)] = g.ae_a.mean() / g.ae_p.mean() - 1
                cells.append(f"{era[(fuel, h, name)]:+10.1%}")
            print(f"{fuel:20s} {h:>2} " + "".join(cells))

    c1 = all(res[(f, h)][1] < 0 for f in DECIDE for h in (2, 3))
    c2 = all(era[(f, h, e[0])] <= 0.01 for f in DECIDE for h in (1, 2, 3) for e in ERAS)
    c3 = all(res[(f, 1)][0] <= 0 for f in DECIDE)
    print(f"\nC1 gain at h=2,3 below zero, both fuels:   {'PASS' if c1 else 'FAIL'}")
    print(f"C2 no era worse than +1% at any h:         {'PASS' if c2 else 'FAIL'}")
    print(f"C3 no proven loss at h=1:                  {'PASS' if c3 else 'FAIL'}")
    print(f"Verdict: {'SHIPS' if c1 and c2 and c3 else 'DOES NOT SHIP'}")

    print("\nDiagnostics, deciding nothing.")
    for fuel in DECIDE:
        d = frames[fuel]
        b = two_lag_model().fit(d, len(d))
        print(f"  {fuel:15s} last cutoff: g1 (x[s-1]) {b[-2]:+.4f}   g2 (x[s-2]) {b[-1]:+.4f}   sum {b[-2] + b[-1]:+.4f}")
    print("  h=1 difference by quintile of the week's own margin move:")
    for fuel in DECIDE:
        d = frames[fuel]
        move = pd.Series(np.abs(own_dev(d) - d.dev.to_numpy()), index=d.index, name="move")
        g = m[(m.fuel == fuel) & (m.h == 1)].merge(move, left_on="date", right_index=True)
        g["q"] = pd.qcut(g.move, 5, labels=[f"Q{i}" for i in range(1, 6)])
        t = g.groupby("q", observed=True).agg(move=("move", "mean"), diff=("diff", "mean"))
        print(f"    {fuel}: " + "  ".join(f"{q} {r.move:4.1f}: {r['diff']:+.3f}" for q, r in t.iterrows()))
    last = prod.date.max()
    view = pd.concat([v[v.date == last].assign(model=k) for k, v in
                      (("production", prod), ("two_lag", two), ("fresh", fresh))])
    print(f"  calls from {last:%d %b %Y}, the newest week of the panel, change in c/L:")
    print(view.pivot_table(index=["fuel", "h"], columns="model", values="nowcast").round(2).to_string())


if __name__ == "__main__":
    main()
