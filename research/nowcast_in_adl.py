"""Does the nowcast improve the FORECAST, or only the cost estimate?

`research/nowcast_brent.py` showed that three trading days of Brent-in-NZD cut
the error on next week's `d_cost` by 17.5% (diesel) / 32.1% (petrol). That is
not the question the report answers. The published forecast is a pump price,
the nowcast reaches it only through the ADL's cost coefficients, and those are
well under 1 — so the gain must shrink, and by how much is the whole question.

WHAT IS CHANGED, AND NOTHING ELSE. `pipeline/backtest.py` is imported rather
than reimplemented, so `load`, `fit_adl`, K, MIN_TRAIN, the Final-only
training filter and the 1.15 retail conversion are identical by construction.
The only new thing is one extra term in the forecast:

    adl_forecast      step j sums b_k * d_cost_{t+j-k} for k >= j
    with the nowcast  the same, for k >= j - 1

because k = j - 1 lands on index t+1 — the week in progress — which is exactly
what the nowcast supplies. It reaches every horizon, not only h=1: at h=1 it
multiplies b0, at h=2 b1, at h=3 b2.

NO LOOK-AHEAD, and this is the part worth checking twice. At cutoff t the
nowcast regression is refit on pairs up to and including t, then applied to
week t+1's partial reading. That reading is observable: MBIE publishes week t
on the Wednesday after it ends, by which point Monday to Wednesday of week t+1
have traded. The ADL coefficients come from `fit_adl(d, t + 1, ...)`, the same
call the production backtest makes.

WHAT WOULD MAKE THIS SHIP. Beating `adl_ecm` on MAE at h=1 and h=2 in
non-crisis weeks, without losing in crisis weeks. `report1_ish` is the
cautionary case: it looked sound until it was scored this way.

Usage:  python research/nowcast_in_adl.py [--days 3]
Offline apart from the Yahoo fetch. No warehouse, no capacity.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "research"))

import backtest as bt                      # noqa: E402
from nowcast_brent import brent_nzd_cpl, week_means   # noqa: E402

NC_MIN_TRAIN = 52


def nowcast_feature(index: pd.DatetimeIndex, days: int) -> np.ndarray:
    """This week's first `days` trading days against last week's full week."""
    m = week_means(brent_nzd_cpl(), index)
    return (m[f"m{days}"] - m.m5.shift(1)).to_numpy()


def forecast_with_nowcast(d: pd.DataFrame, t: int, beta: np.ndarray, h: int,
                          with_ecm: bool, nc: float) -> float:
    """`bt.adl_forecast`, with index t+1 supplied by the nowcast."""
    dc = d.d_cost.to_numpy()
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(max(0, j - 1), bt.K + 1):
            idx = t + j - k
            val = nc if idx == t + 1 else (dc[idx] if idx <= t else np.nan)
            if idx < 0 or not np.isfinite(val):
                return np.nan
            step += beta[1 + k] * val
        if with_ecm:
            dev = d.dev.to_numpy()[t]
            if not np.isfinite(dev):
                return np.nan
            step += beta[-1] * dev
        total += step
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3,
                    help="trading days of the week in progress that are in hand")
    ap.add_argument("--placebo", action="store_true",
                    help="feed LAST week's reading instead of the week in "
                         "progress. That information is already inside "
                         "d_cost_t, so a gain here would mean the extra term "
                         "is helping for some reason other than new "
                         "information, and the whole result is plumbing.")
    ap.add_argument("--save", action="store_true",
                    help="write the per-week results to data/ for the chart")
    args = ap.parse_args()

    rows = []
    for fuel in ("Diesel", "Regular Petrol", "Premium Petrol 95R"):
        d = bt.load(fuel)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        hi = (d.crude_vol_regime == "high").to_numpy()
        is_final = d.is_final.to_numpy()

        x = nowcast_feature(pd.DatetimeIndex(d.index), args.days)
        y = d.d_cost.to_numpy()

        # Position inside a volatility episode, for the onset breakdown. Both
        # the regime and the episode id come from a CENTRED window and see
        # four weeks ahead, so this may split results and must never choose a
        # model in real time — the same rule the backtest already applies to
        # `hi`.
        ep = d.crude_episode_id.to_numpy()
        phase = np.full(len(d), np.nan)
        seen: dict = {}
        for i, e in enumerate(ep):
            if isinstance(e, str) and e:
                seen[e] = seen.get(e, 0) + 1
                phase[i] = seen[e]

        for t in range(bt.MIN_TRAIN, n):
            b_ecm = bt.fit_adl(d, t + 1, with_ecm=True)
            if b_ecm is None:
                continue

            # The nowcast, refit on everything up to t and applied to t+1.
            nc = np.nan
            src = t if args.placebo else t + 1
            if t + 1 < n and np.isfinite(x[src]):
                ok = (np.isfinite(x[:t + 1]) & np.isfinite(y[:t + 1])
                      & is_final[:t + 1])
                if ok.sum() >= NC_MIN_TRAIN:
                    A = np.column_stack([np.ones(ok.sum()), x[:t + 1][ok]])
                    g = np.linalg.lstsq(A, y[:t + 1][ok], rcond=None)[0]
                    nc = g[0] + g[1] * x[src]

            for h in bt.HORIZONS:
                actual = (retail[t + h] - retail[t]) if t + h < n else np.nan
                e = bt.adl_forecast(d, t, b_ecm, h, True)
                e_nc = (forecast_with_nowcast(d, t, b_ecm, h, True, nc)
                        if np.isfinite(nc) else np.nan)
                rows.append(dict(
                    fuel=fuel, date=d.index[t], h=h, actual=actual, hi=hi[t],
                    episode=ep[t] if isinstance(ep[t], str) else None,
                    phase=phase[t],
                    outcome_known=bool(np.isfinite(actual)),
                    naive=0.0,
                    adl_ecm=e * 1.15 if np.isfinite(e) else np.nan,
                    adl_ecm_nc=e_nc * 1.15 if np.isfinite(e_nc) else np.nan,
                ))

    res = pd.DataFrame(rows)
    if args.save:
        out = ROOT / "data" / "nowcast_results.csv"
        res.to_csv(out, index=False)
        print(f"{len(res)} rows -> {out}", file=sys.stderr)
    ev = res[res.outcome_known]
    methods = ["naive", "adl_ecm", "adl_ecm_nc"]

    tag = "PLACEBO: last week's reading" if args.placebo else \
        f"{args.days} trading day(s) of the week in progress"
    print(f"\nNowcast from {tag}.")
    print("MAE in c/L on the pump price; lower is better.\n")

    for fuel in ("Diesel", "Regular Petrol", "Premium Petrol 95R"):
        for label, sub in (("ALL", ev[ev.fuel == fuel]),
                           ("non-crisis", ev[(ev.fuel == fuel) & ~ev.hi]),
                           ("crisis", ev[(ev.fuel == fuel) & ev.hi])):
            s_all = sub.dropna(subset=methods)
            if s_all.empty:
                continue
            print(f"{fuel} — {label}")
            print(f"  {'h':>2} {'n':>5} " + "".join(f"{m:>13}" for m in methods)
                  + f"{'nc vs ecm':>12}")
            for h in bt.HORIZONS:
                s = s_all[s_all.h == h]
                if s.empty:
                    continue
                maes = [np.abs(s[m] - s.actual).mean() for m in methods]
                delta = (1 - maes[2] / maes[1]) * 100
                print(f"  {h:>2} {len(s):>5} "
                      + "".join(f"{v:>13.3f}" for v in maes)
                      + f"{delta:>11.1f}%")
            print()

    # The onset breakdown: the model's worst weeks are the ones where a
    # forecast is worth having, so an average that hides them is the wrong
    # average.
    print("Crisis weeks by position in the episode — h=2, MAE c/L")
    print(f"  {'fuel':<16}{'phase':>12} {'n':>4} {'naive':>8} {'adl_ecm':>9}"
          f" {'+nowcast':>10} {'gain':>7}")
    bands = (("weeks 1-2", 1, 2), ("weeks 3-4", 3, 4), ("weeks 5+", 5, 999))
    for fuel in ("Diesel", "Regular Petrol"):
        for label, lo, hi_ in bands:
            s = ev[(ev.fuel == fuel) & (ev.h == 2) & ev.hi
                   & ev.phase.between(lo, hi_)].dropna(subset=methods)
            if len(s) < 5:
                continue
            maes = [np.abs(s[m] - s.actual).mean() for m in methods]
            print(f"  {fuel:<16}{label:>12} {len(s):>4} {maes[0]:>8.3f}"
                  f" {maes[1]:>9.3f} {maes[2]:>10.3f}"
                  f" {(1 - maes[2] / maes[1]) * 100:>6.1f}%")
    print()

    # And the tail: the weeks the price actually moved most, wherever they sit.
    print("Largest actual moves — h=2, by decile of |actual|, MAE c/L")
    for fuel in ("Diesel", "Regular Petrol"):
        s = ev[(ev.fuel == fuel) & (ev.h == 2)].dropna(subset=methods).copy()
        s["band"] = pd.qcut(s.actual.abs(), 10, labels=False, duplicates="drop")
        for band, name in ((9, "top 10%"), (8, "next 10%")):
            b = s[s.band == band]
            if b.empty:
                continue
            maes = [np.abs(b[m] - b.actual).mean() for m in methods]
            print(f"  {fuel:<16}{name:>12} {len(b):>4} {maes[0]:>8.3f}"
                  f" {maes[1]:>9.3f} {maes[2]:>10.3f}"
                  f" {(1 - maes[2] / maes[1]) * 100:>6.1f}%")
    print()

    print("Weeks in which the nowcast version is closer than plain adl_ecm:")
    for fuel in ("Diesel", "Regular Petrol"):
        for h in bt.HORIZONS:
            s = ev[(ev.fuel == fuel) & (ev.h == h)].dropna(subset=methods)
            if s.empty:
                continue
            win = (np.abs(s.adl_ecm_nc - s.actual)
                   < np.abs(s.adl_ecm - s.actual)).mean()
            print(f"  {fuel:<16} h={h}  {100 * win:5.1f}%  (n={len(s)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
