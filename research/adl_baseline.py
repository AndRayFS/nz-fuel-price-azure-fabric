"""Baseline distributed-lag model: how a landed-cost move reaches the pump.

Steps 2-4 of the plan in docs/architecture.md. Deliberately the simplest
thing that could work, so that later additions (error correction,
asymmetry, regime interaction) can be judged against it.

    d_net_t = a + sum_{k=0..K} b_k * d_cost_{t-k} + e_t

TARGET is the *commercial* part of the price:

    net = adjusted_retail_price - taxes - gst - ets

  * `adjusted_retail_price`, not `board_price` — the margin identity closes
    on it exactly (0.000 c/L from 2010); board misses by 4.8-7.0.
  * taxes out because the March 2022 excise cut (-25.0 c/L over two weeks)
    is the single largest move in the dataset and is not a market event.
    Verified harmless: net-of-tax moves only -1.02 c/L across that span.
  * GST out because it is 15% of everything else and would inflate every
    coefficient by that factor.
  * ETS out because it is the NZU carbon price, an asset price on a random
    walk, unrelated to crude.

  To read any coefficient below as a pump-price effect:
    d_pump = (d_cost + d_margin + d_ets) * 1.15 + d_taxes

FACTOR is `importer_cost`, not crude. Crude is two steps upstream: it
reaches the pump only through the Singapore product spot, and the
crude-to-product spread did 52-78% of the 2026 crisis move on its own.

CHANGES, not levels: both series trend, and margin levels have tripled
since 2004.

SAMPLE is the import era (Apr 2022+). Marsden Point stopped refining
31 Mar 2022, MBIE changed its retail source 1 Jan 2022, and before 2010
the published components do not reconcile at all. See
research/period_labelling_brief.md.

LAG LENGTH K is chosen by BIC, and that rule is fixed before looking at
any output — otherwise K gets picked for the prettiest weights. (BIC is
computed under iid likelihood while inference uses HAC; that mismatch is
conventional and affects selection, not the reported errors.)

STANDARD ERRORS are Newey-West (HAC). Weekly cost changes are
autocorrelated and every lag of the same move enters K+1 consecutive rows,
so the effective sample is far smaller than n and ordinary errors would
overstate significance. Bandwidth K+2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller

PANEL = Path(__file__).parent / "data" / "panel_weekly.csv"
IMPORT_ERA = "2022-04-01"
K_MAX = 8
FUELS = ["Regular Petrol", "Diesel"]


def build(fuel: str, start: str = IMPORT_ERA) -> pd.DataFrame:
    df = pd.read_csv(PANEL, parse_dates=["Date"])
    d = df[df.Fuel == fuel].sort_values("Date").set_index("Date").copy()
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    # Difference on the FULL history, then trim: differencing after the cut
    # would silently drop the first week of the sample.
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["d_crude"] = d.dubai_crude_nzd.diff()
    return d[d.index >= start]


def fit(d: pd.DataFrame, k: int, factor: str = "d_cost"):
    X = pd.concat({f"lag{i}": d[factor].shift(i) for i in range(k + 1)}, axis=1)
    frame = pd.concat([d.d_net, X], axis=1).dropna()
    y = frame.d_net
    X = sm.add_constant(frame.drop(columns="d_net"))
    return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": k + 2})


def cumulative(res, k: int) -> tuple[float, float]:
    """Sum of the lag weights and its HAC standard error."""
    c = np.zeros(len(res.params))
    c[1:] = 1.0  # every lag, excluding the intercept
    total = float(c @ res.params)
    se = float(np.sqrt(c @ res.cov_params() @ c))
    return total, se


def main() -> None:
    for fuel in FUELS:
        d = build(fuel)
        print(f"\n{'=' * 66}\n{fuel} — import era, {len(d)} weeks "
              f"({d.index.min().date()} to {d.index.max().date()})\n{'=' * 66}")

        for name in ("d_net", "d_cost"):
            stat, p, *_ = adfuller(d[name].dropna(), autolag="AIC")
            print(f"  ADF {name:7s}: stat {stat:7.2f}, p {p:.4f}"
                  f"{'  (stationary)' if p < 0.05 else '  (NOT stationary)'}")

        # K by BIC, on a common sample so the criterion is comparable.
        common = fit(d, K_MAX).nobs
        bics = {}
        for k in range(K_MAX + 1):
            X = pd.concat({f"lag{i}": d.d_cost.shift(i) for i in range(k + 1)}, axis=1)
            frame = pd.concat([d.d_net, X], axis=1).dropna().iloc[-int(common):]
            m = sm.OLS(frame.d_net, sm.add_constant(frame.drop(columns="d_net"))).fit()
            bics[k] = m.bic
        k_star = min(bics, key=bics.get)
        print("\n  BIC by K: " + "  ".join(f"{k}:{v:.1f}" for k, v in bics.items()))
        print(f"  -> K = {k_star}")

        res = fit(d, k_star)
        print(f"\n  weight   coef    HAC se    t      p")
        for i in range(k_star + 1):
            p_ = res.params[f"lag{i}"]
            se = res.bse[f"lag{i}"]
            print(f"  lag {i}   {p_:6.3f}   {se:5.3f}   {p_ / se:6.2f}  "
                  f"{res.pvalues[f'lag{i}']:.3f}")
        tot, tot_se = cumulative(res, k_star)
        print(f"  ------------------------------------------")
        print(f"  total   {tot:6.3f}   {tot_se:5.3f}   {tot / tot_se:6.2f}"
              f"   [{tot - 1.96 * tot_se:.3f}, {tot + 1.96 * tot_se:.3f}]")
        print(f"  R2 {res.rsquared:.3f}   n {int(res.nobs)}")

        # Centre of mass: how many weeks, on average, a cost move takes to
        # arrive. Only meaningful if the weights are mostly positive.
        w = np.array([res.params[f"lag{i}"] for i in range(k_star + 1)])
        if w.sum() > 0:
            print(f"  centre of mass: {float((w * np.arange(len(w))).sum() / w.sum()):.2f} weeks")

        # Was switching the factor from crude worth it? Same K, same sample.
        alt = fit(d, k_star, factor="d_crude")
        a_tot, a_se = cumulative(alt, k_star)
        print(f"\n  same model on CRUDE instead: R2 {alt.rsquared:.3f}"
              f"  (vs {res.rsquared:.3f}), total {a_tot:.3f} +/- {a_se:.3f}")


if __name__ == "__main__":
    main()
