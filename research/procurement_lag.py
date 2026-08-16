"""Does OLD crude move the pump price, beyond today's replacement cost?

`Importer cost` is what importing would cost *this week* — this week's
Singapore product spot at this week's FX, with no purchase date and no
voyage time anywhere in it (docs/mbie_notes.md). The fuel actually in the
tanks was bought weeks earlier at a different price.

So: if retailers price off what they *paid*, crude from 4–12 weeks ago
should move the pump price on top of current replacement cost. If they
price off replacement cost — as fuel retail generally does — old crude
should add nothing, because everything it implies is already in the
landed-cost number.

    d_net = a + sum_k b_k d_cost_{t-k} + g*dev + THETA * d_oldcrude + e

WHAT THE ANSWER DECIDES

  nothing added  -> replacement-cost pricing; `importer_cost` is the right
                    factor; the physical procurement lag lands in MARGIN,
                    not in price (consistent with yesterday's finding that
                    procurement timing is invisible as cost and shows up as
                    margin); the lag we publish is the whole consumer story.
  something added-> our factor understates the lag, AND the forecast
                    horizon extends: old crude is already known at forecast
                    time, so a real coefficient on it buys reach beyond the
                    current 1-3 weeks.

TWO FORMS, because a thin effect spread over nine lags would vanish from
nine separate t-tests:

  1. ONE variable — the change in average crude over weeks t-12..t-4.
     Physically the better match: cargoes are bought continuously and
     conventionally priced on an average over a window, not on one day.
     All the signal lands in one coefficient, so this has the most power.
  2. NINE lags plus a joint Wald test that all are zero. A control, in case
     the effect concentrates at one specific horizon rather than spreading.

Crude is converted to c/L (x0.629, 1 bbl = 158.987 L) so its coefficient is
directly comparable to the cost coefficients: 1.0 would mean old crude
passes through as completely as current landed cost does.

WHY OSCILLATION IN CRUDE DOES NOT HIDE THE EFFECT — it is what makes the
test possible. Regressors are separable only when they differ; smooth
one-way movement in crude would make lags 4..12 near-identical and
unidentifiable. Weekly crude changes lose autocorrelation after ~2 weeks
(0.33 at lag 1, ~0 beyond lag 3), so the old-crude block is close to
orthogonal to current cost, which is exactly the condition this test needs.

WHAT A NULL RESULT WILL NOT MEAN. If procurement timing itself varies —
cargoes bought six weeks ahead one month and ten the next, voyages of
different lengths — the effect is smeared across lags *and* moves around in
time, which a fixed-lag regression sees poorly. A null here means "no
stable effect at a fixed horizon", not "physical procurement never reaches
the price". The detectable magnitude is reported so the null has a size.
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
LO, HI = 4, 12          # procurement window, weeks back
CPL = 0.629             # c/L per NZD/bbl


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
    crude = d.dubai_crude_nzd * CPL
    d["d_crude"] = crude.diff()
    # Average crude level over weeks t-HI .. t-LO, then differenced: the
    # change in the historical cost basis of fuel being sold now.
    span = HI - LO + 1
    d["d_oldcrude"] = crude.rolling(span).mean().shift(LO).diff()
    d["dev"] = (d.importer_margin
                - d.importer_margin.rolling(ECM_WINDOW, min_periods=ECM_WINDOW).mean()
                ).shift(1)
    return d[d.index >= START]


def base_cols(d: pd.DataFrame) -> dict:
    cols = {f"cost{i}": d.d_cost.shift(i) for i in range(K + 1)}
    cols["dev"] = d.dev
    cols["datamine"] = (d.data_regime == "datamine").astype(float)
    return cols


def fit(d: pd.DataFrame, extra: dict | None):
    cols = base_cols(d)
    if extra:
        cols.update(extra)
    frame = pd.concat([d.d_net, pd.DataFrame(cols)], axis=1).dropna()
    return sm.OLS(frame.d_net,
                  sm.add_constant(frame.drop(columns="d_net"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": K + 2}), frame


def main() -> None:
    for fuel in ("Regular Petrol", "Diesel"):
        d = load(fuel)
        print(f"\n{'=' * 68}\n{fuel} — 2010+, crude in c/L equivalent\n{'=' * 68}")

        # Common sample so R2 is comparable across specifications.
        _, frame_full = fit(d, {f"oc{i}": d.d_crude.shift(i)
                                for i in range(LO, HI + 1)} |
                            {"d_oldcrude": d.d_oldcrude})
        keep = frame_full.index
        dd = d.loc[keep]

        base, _ = fit(dd, None)
        print(f"  baseline (cost lags 0-{K} + ECM)      R2 {base.rsquared:.4f}  "
              f"n {int(base.nobs)}")

        one, _ = fit(dd, {"d_oldcrude": dd.d_oldcrude})
        th = one.params["d_oldcrude"]
        se = one.bse["d_oldcrude"]
        print(f"\n  FORM 1 — average crude, weeks {LO}-{HI} back, one term")
        print(f"    coefficient {th:+.4f}  HAC se {se:.4f}  t {th/se:+.2f}  "
              f"p {one.pvalues['d_oldcrude']:.4f}")
        print(f"    95% CI [{th-1.96*se:+.4f}, {th+1.96*se:+.4f}]   "
              f"R2 {one.rsquared:.4f}  (delta {one.rsquared-base.rsquared:+.4f})")
        print(f"    detectable at 95%: any true effect above "
              f"{1.96*se:.3f} c/L per c/L of old crude")

        blk = {f"oc{i}": dd.d_crude.shift(i) for i in range(LO, HI + 1)}
        many, _ = fit(dd, blk)
        names = [f"oc{i}" for i in range(LO, HI + 1)]
        R = np.zeros((len(names), len(many.params)))
        for r_, nm in enumerate(names):
            R[r_, list(many.params.index).index(nm)] = 1.0
        w = many.f_test(R)
        print(f"\n  FORM 2 — {len(names)} separate lags, joint test")
        print("    " + "  ".join(f"{i}:{many.params[f'oc{i}']:+.3f}"
                                 for i in range(LO, HI + 1)))
        print(f"    joint F {float(w.fvalue):.2f}  p {float(w.pvalue):.4f}   "
              f"R2 {many.rsquared:.4f}  (delta {many.rsquared-base.rsquared:+.4f})")
        s = sum(many.params[n] for n in names)
        c = np.array([1.0 if n in names else 0.0 for n in many.params.index])
        s_se = float(np.sqrt(c @ many.cov_params() @ c))
        print(f"    sum of the block {s:+.3f} +/- {s_se:.3f}")


if __name__ == "__main__":
    main()
