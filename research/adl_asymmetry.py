"""Step 6: rockets and feathers, tested properly this time.

Do pump prices follow cost RISES faster or more completely than cost FALLS?
Three earlier attempts in this project found an asymmetry and none
survived: two died to range restriction (the up and down samples had
different spreads, so `r` was not comparable) and one to measurement error
in a rounded factor biasing the small-move slope toward zero.

This attempt differs in the one way that matters: rises and falls are
estimated **in the same regression**, so they share a sample, a target and
an error term, and the difference between them gets a standard error
instead of an eyeball.

    d_net = a + sum_k bp_k * pos_{t-k} + sum_k bn_k * neg_{t-k} + g*dev

    pos = max(d_cost, 0)      neg = min(d_cost, 0)

Under symmetry bp_k == bn_k at every lag. Both are "cents of price per cent
of cost", so they are directly comparable and a Wald test on their sums is
the test.

PRE-REGISTERED, before running. Rockets and feathers predicts EITHER
  (a) sum(bp) > sum(bn)   — more of a rise is passed on than of a fall, or
  (b) centre of mass of bp < that of bn — rises arrive sooner.
Reported either way, including if the sign comes out backwards. A p-value
above 0.05 on the sum difference will be reported as "no asymmetry
detected", not as "symmetry proven": with this sample the test can miss a
real effect of a few hundredths.

K = 6, not BIC-selected. Above K=6 the high-volatility regime's estimate
stops being identified (docs/architecture.md), and K=6 is where the two
regimes still agree. Choosing the lag length by a criterion that the
crisis weeks destabilise would import that instability into the asymmetry
test.

Sample 2010+, where the published components reconcile exactly, with a
`data_regime` dummy for the 2022 measurement break.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = Path(__file__).parent
K = 6
ECM_WINDOW = 104
START = "2010-01-01"


def load(fuel: str) -> pd.DataFrame:
    p = pd.read_csv(HERE / "data" / "panel_weekly.csv", parse_dates=["Date"])
    f = pd.read_csv(HERE.parent / "seeds" / "period_flags.csv",
                    parse_dates=["week_date"])
    d = p[p.Fuel == fuel].merge(
        f[f.fuel == fuel], left_on="Date", right_on="week_date", how="left"
    ).sort_values("Date").set_index("Date")
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["dev"] = (d.importer_margin
                - d.importer_margin.rolling(ECM_WINDOW, min_periods=ECM_WINDOW).mean()
                ).shift(1)
    return d[d.index >= START]


def fit(d: pd.DataFrame, with_ecm: bool = True):
    pos = d.d_cost.clip(lower=0)
    neg = d.d_cost.clip(upper=0)
    cols = {}
    for i in range(K + 1):
        cols[f"up{i}"] = pos.shift(i)
        cols[f"dn{i}"] = neg.shift(i)
    if with_ecm:
        cols["dev"] = d.dev
    cols["datamine"] = (d.data_regime == "datamine").astype(float)
    frame = pd.concat([d.d_net, pd.DataFrame(cols)], axis=1).dropna()
    res = sm.OLS(frame.d_net,
                 sm.add_constant(frame.drop(columns="d_net"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": K + 2})
    return res, frame


def contrast(res, prefix: str) -> tuple[float, float]:
    c = np.array([1.0 if n.startswith(prefix) else 0.0 for n in res.params.index])
    return float(c @ res.params), float(np.sqrt(c @ res.cov_params() @ c))


def com(res, prefix: str) -> float:
    w = np.array([res.params[f"{prefix}{i}"] for i in range(K + 1)])
    return float((w * np.arange(K + 1)).sum() / w.sum()) if w.sum() != 0 else np.nan


def main() -> None:
    for fuel in ("Regular Petrol", "Diesel"):
        d = load(fuel)
        res, frame = fit(d)
        n_up = int((frame[[f"up{i}" for i in range(1)]].iloc[:, 0] > 0).sum())
        n_dn = int((frame[[f"dn{i}" for i in range(1)]].iloc[:, 0] < 0).sum())
        print(f"\n{'=' * 64}\n{fuel} — 2010+, n={int(res.nobs)} "
              f"({n_up} weeks cost up, {n_dn} down)\n{'=' * 64}")

        print("  lag      rise     fall     difference")
        for i in range(K + 1):
            bp, bn = res.params[f"up{i}"], res.params[f"dn{i}"]
            cv = np.zeros(len(res.params))
            cv[list(res.params.index).index(f"up{i}")] = 1
            cv[list(res.params.index).index(f"dn{i}")] = -1
            se = float(np.sqrt(cv @ res.cov_params() @ cv))
            print(f"   {i}     {bp:+6.3f}   {bn:+6.3f}   {bp - bn:+6.3f} "
                  f"(t {(bp - bn) / se:+5.2f})")

        up, up_se = contrast(res, "up")
        dn, dn_se = contrast(res, "dn")
        cv = np.array([1.0 if n.startswith("up") else (-1.0 if n.startswith("dn") else 0.0)
                       for n in res.params.index])
        diff = float(cv @ res.params)
        diff_se = float(np.sqrt(cv @ res.cov_params() @ cv))
        from scipy import stats
        p = 2 * (1 - stats.norm.cdf(abs(diff / diff_se)))
        print(f"\n  total on rises  {up:+.3f} +/- {up_se:.3f}")
        print(f"  total on falls  {dn:+.3f} +/- {dn_se:.3f}")
        print(f"  difference      {diff:+.3f} +/- {diff_se:.3f}  "
              f"(t {diff / diff_se:+.2f}, p {p:.4f})")
        print(f"  centre of mass: rises {com(res, 'up'):.2f} wk, "
              f"falls {com(res, 'dn'):.2f} wk")
        print(f"  ECM g {res.params['dev']:+.4f} "
              f"(t {res.params['dev'] / res.bse['dev']:+.2f})   R2 {res.rsquared:.3f}")


if __name__ == "__main__":
    main()
