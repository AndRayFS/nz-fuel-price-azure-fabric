"""M2 of the 19 Nov 2026 review: does the margin correct at a different speed
above its norm than below it?

The four asymmetry tests in docs/research.md ("Rockets and feathers, fourth
attempt", 15 Aug 2026) split the COST changes into rises and falls and kept
one ECM term. None split the ECM term itself, which is the reviewer's
mechanism: with the margin far above its norm, a symmetric `g * dev` may
pull the price down faster than it falls.

    symmetric    ... + g * dev
    asymmetric   ... + g_hi * max(dev, 0) + g_lo * min(dev, 0)

`dev` is production's: the margin's distance from its trailing 104-week mean,
lagged one week. g is negative; "feathers" is g_hi closer to zero than g_lo.

PRE-REGISTERED, written before the first run, 23 Nov 2026:
  1. In-sample, production specification (K=6, Final rows, 2010+), per fuel:
     g_hi - g_lo with a 12-week moving-block bootstrap 95% interval.
     Asymmetry is detected only if the interval excludes zero.
  2. Walk-forward, the nowcast path Report 1 plots, every call since Feb 2013:
     the asymmetric ECM ships only if it beats the symmetric one on MAE at
     h=1 and h=2 in non-crisis weeks without losing in crisis weeks, for both
     Regular Petrol and Diesel — the criterion the nowcast itself passed.
  3. Diagnostic, decides nothing: mean signed error (actual - call) on calls
     of more than 10 c/L either way, where the review's example sits.

A SEPARATE QUESTION, reported apart and never combined with the above.
`adl_forecast` and `forecast_with_nowcast` take the ECM term as `dev[t]`,
which is the margin of week t-1: `dev` is shifted one week so that the fit
pairs d_net[s] with the margin of s-1. For the first step of a call made at
t, the fitted pairing asks for the margin of week t, which is published with
week t and so known. Variant `fresh` uses it, for every step, as production
uses dev[t] for every step. Only the forecast changes; the fit does not.

Usage:  python research/review_m2_asym_ecm.py
Offline. Same inputs as research/wf_harness.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wf_harness as wf

bt = wf.bt


def design(d: pd.DataFrame, asym: bool) -> np.ndarray:
    cols = [d.d_cost.shift(i).to_numpy() for i in range(bt.K + 1)]
    dev = d.dev.to_numpy()
    if asym:
        cols += [np.where(np.isfinite(dev), np.maximum(dev, 0), np.nan),
                 np.where(np.isfinite(dev), np.minimum(dev, 0), np.nan)]
    else:
        cols.append(dev)
    return np.column_stack([np.ones(len(d))] + cols)


def fit(d: pd.DataFrame, upto: int, asym: bool):
    """bt.fit_adl(with_ecm=True), with the ECM column optionally split."""
    X = design(d, asym)[:upto]
    y = d.d_net.to_numpy()[:upto]
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()[:upto]
    if ok.sum() < bt.MIN_TRAIN:
        return None
    return bt.ols(y[ok], X[ok])


def ecm_step(beta: np.ndarray, dev: float, asym: bool) -> float:
    if asym:
        return beta[-2] * max(dev, 0.0) + beta[-1] * min(dev, 0.0)
    return beta[-1] * dev


def forecast(d, t, beta, h, ncv, asym: bool, dev_at: np.ndarray):
    """bt.adl_forecast (ncv nan) or nowcast.forecast_with_nowcast (ncv
    finite), with the ECM term pluggable. `dev_at[t]` is the deviation the
    call at t uses."""
    dc = d.d_cost.to_numpy()
    use_nc = np.isfinite(ncv)
    dev = dev_at[t]
    if not np.isfinite(dev):
        return np.nan
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(max(0, j - 1) if use_nc else j, bt.K + 1):
            idx = t + j - k
            val = ncv if (use_nc and idx == t + 1) else (dc[idx] if idx <= t else np.nan)
            if idx < 0 or not np.isfinite(val):
                return np.nan
            step += beta[1 + k] * val
        step += ecm_step(beta, dev, asym)
        total += step
    return total


def model(name: str, asym: bool, fresh: bool) -> wf.Model:
    cache: dict = {}

    def dev_at(d):
        key = id(d)
        if key not in cache:
            if fresh:
                m = d.importer_margin
                cache[key] = (m - m.rolling(bt.ECM_WINDOW, min_periods=bt.ECM_WINDOW).mean()).to_numpy()
            else:
                cache[key] = d.dev.to_numpy()
        return cache[key]

    return wf.Model(name, lambda d, upto: fit(d, upto, asym),
                    lambda d, t, b, h, ncv: forecast(d, t, b, h, ncv, asym, dev_at(d)))


def in_sample(frames: dict) -> None:
    print("1. In-sample, Final rows 2010+, K=6. g < 0 pulls the price toward the norm.")
    print(f"   {'fuel':20s} {'n':>5} {'dev>0':>6} {'g sym':>8} {'g_hi':>8} {'g_lo':>8} "
          f"{'g_hi - g_lo':>12} {'95% block CI':>18}")
    for fuel, d in frames.items():
        X = design(d, True)
        y = d.d_net.to_numpy()
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()
        Xo, yo = X[ok], y[ok]
        b = bt.ols(yo, Xo)
        bs = fit(d, len(d), asym=False)
        rows = np.column_stack([yo, Xo])
        lo, hi = wf.block_bootstrap_ci(rows, lambda r: (lambda bb: bb[-2] - bb[-1])(bt.ols(r[:, 0], r[:, 1:])))
        print(f"   {fuel:20s} {len(yo):>5} {int((Xo[:, -2] > 0).sum()):>6} {bs[-1]:+8.4f} {b[-2]:+8.4f} "
              f"{b[-1]:+8.4f} {b[-2] - b[-1]:+12.4f}   [{lo:+.4f}, {hi:+.4f}]")


def score(res: pd.DataFrame, label: str) -> pd.DataFrame:
    r = res[res.outcome_known & (res.date >= "2013-02-01")].copy()
    r["ae"] = (r.actual - r.nowcast).abs()
    return r.assign(model=label)


def main() -> None:
    frames = wf.production_frames()

    # plumbing: the pluggable forecast with the symmetric term is production
    sym = wf.walk_forward(frames, model("sym", asym=False, fresh=False))
    prod = wf.walk_forward(frames)
    gap = (sym.nowcast - prod.nowcast).abs().max()
    assert gap < 1e-9, f"symmetric variant is not production: {gap}"
    # and `fresh` really is dev one week on
    for d in frames.values():
        m = d.importer_margin
        x = (m - m.rolling(bt.ECM_WINDOW, min_periods=bt.ECM_WINDOW).mean())
        both = pd.concat([x, d.dev.shift(-1)], axis=1).dropna()
        assert (both.iloc[:, 0] - both.iloc[:, 1]).abs().max() < 1e-9
    print(f"plumbing: symmetric = production to {gap:.1e}; fresh dev = dev[t+1]\n")

    in_sample(frames)

    asym = wf.walk_forward(frames, model("asym", asym=True, fresh=False))
    fresh = wf.walk_forward(frames, model("fresh", asym=False, fresh=True))
    s = pd.concat([score(sym, "sym"), score(asym, "asym"), score(fresh, "fresh")])

    print("\n2. Walk-forward, nowcast path, calls since Feb 2013. MAE c/L.")
    print(f"   {'fuel':20s} {'h':>2} {'regime':>10} {'n':>4} {'sym':>7} {'asym':>7} {'asym vs':>8} "
          f"| {'fresh':>7} {'fresh vs':>8}")
    for fuel in wf.FUELS:
        for h in (1, 2, 3):
            for reg, mask in (("non-crisis", lambda g: ~g.hi), ("crisis", lambda g: g.hi), ("all", lambda g: g.hi | ~g.hi)):
                g = s[(s.fuel == fuel) & (s.h == h)]
                g = g[mask(g)]
                mae = g.groupby("model").ae.mean()
                print(f"   {fuel:20s} {h:>2} {reg:>10} {int(len(g) / 3):>4} {mae['sym']:7.3f} {mae['asym']:7.3f} "
                      f"{mae['asym'] / mae['sym'] - 1:+8.1%} | {mae['fresh']:7.3f} {mae['fresh'] / mae['sym'] - 1:+8.1%}")

    print("\n3. Diagnostic: mean signed error (actual - call), calls of more than 10 c/L, h=1, all fuels.")
    w = s[s.h == 1].copy()
    w["call"] = w.groupby(["fuel", "date"]).nowcast.transform(lambda v: v.iloc[0])  # sym's call defines the bin
    for side, mask in (("call < -10", w.call < -10), ("call > +10", w.call > 10)):
        g = w[mask]
        print(f"   {side}: n={int(len(g) / 3)}  " + "  ".join(
            f"{m} {(g[g.model == m].actual - g[g.model == m].nowcast).mean():+.2f}" for m in ("sym", "asym", "fresh")))

    live = pd.concat([sym.assign(model="sym"), asym.assign(model="asym"), fresh.assign(model="fresh")])
    last = live[live.date == live.date.max()]
    print(f"\n   Calls from the newest week of the panel ({live.date.max():%d %b %Y}), change in c/L:")
    print(last.assign(chg=last.nowcast).pivot_table(index=["fuel", "h"], columns="model", values="chg").round(2).to_string())


if __name__ == "__main__":
    main()
