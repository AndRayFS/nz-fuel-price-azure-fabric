"""All headline numbers, recomputed on FINAL data only. The canonical set.

Everything published before 16 Aug 2026 was computed on a sample that
included weeks MBIE has not finalised. Those weeks demonstrably destabilise
the estimate (docs/architecture.md), and MBIE's own pages explain why: it
suspended `Importer cost` and `Importer margin` from 18 Mar to 1 Jul 2026,
backfilled them, and everything from 1 Apr stays Provisional until Stats NZ
publishes the quarter's CPI.

The cutoff is read from the data, not hardcoded, so this script becomes
correct again by itself once those weeks finalise: re-run
`export_panel.py`, then re-run this.

Sample: every series the regressions read is Final (`FINAL_STATUS_COLS`
below — status is published per variable, not per week) AND 2010+ (before
2010 the published components do not reconcile — see docs/mbie_notes.md).

Prints the all-data figure beside each Final-only one, because the point is
not just to have better numbers but to know which of them moved.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = Path(__file__).parent
K_MAIN = 6
ECM_WINDOW = 104
START = "2010-01-01"
FUELS = ("Regular Petrol", "Diesel")

# The sample filter, stated as the variables it depends on. Same six as
# backtest.py's TRAIN_STATUS_COLS, and for the same reason: MBIE publishes
# status per value, so a week is "Final" here only in the sense that every
# series this regression reads is. Deliberately duplicated rather than
# imported — backtest.py is the weekly production path and this is not, and
# W5 separates them.
FINAL_STATUS_COLS = (
    "adjusted_retail_price_status",
    "taxes_status",
    "gst_status",
    "ets_status",
    "importer_cost_status",
    "importer_margin_status",
)


def all_final(p: pd.DataFrame) -> pd.Series:
    """True where every series the regressions read is Final."""
    ok = pd.Series(True, index=p.index)
    for c in FINAL_STATUS_COLS:
        ok &= p[c].eq("Final")
    return ok


def load(fuel: str, final_only: bool) -> pd.DataFrame:
    p = pd.read_csv(HERE / "data" / "panel_weekly.csv", parse_dates=["Date"])
    f = pd.read_csv(HERE.parent / "seeds" / "period_flags.csv",
                    parse_dates=["week_date"])
    d = p[p.Fuel == fuel].merge(
        f[f.fuel == fuel][["week_date", "crude_vol_regime"]],
        left_on="Date", right_on="week_date", how="left"
    ).sort_values("Date").set_index("Date")
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["dev"] = (d.importer_margin
                - d.importer_margin.rolling(ECM_WINDOW, min_periods=ECM_WINDOW).mean()
                ).shift(1)
    d["hi"] = (d.crude_vol_regime == "high").astype(float)
    d = d[d.index >= START]
    return d[all_final(d)] if final_only else d


def fit(d, k, extra=None, ecm=True):
    cols = {f"l{i}": d.d_cost.shift(i) for i in range(k + 1)}
    if ecm:
        cols["dev"] = d.dev
    cols["datamine"] = (d.data_regime == "datamine").astype(float) \
        if "data_regime" in d else 0.0
    if extra:
        cols.update(extra)
    frame = pd.concat([d.d_net, pd.DataFrame(cols)], axis=1).dropna()
    res = sm.OLS(frame.d_net,
                 sm.add_constant(frame.drop(columns="d_net"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": k + 2})
    return res, frame


def lag_sum(res, prefix="l"):
    c = np.array([1.0 if n.startswith(prefix) and n[len(prefix):].isdigit()
                  else 0.0 for n in res.params.index])
    return float(c @ res.params), float(np.sqrt(c @ res.cov_params() @ c))


def main() -> None:
    p = pd.read_csv(HERE / "data" / "panel_weekly.csv", parse_dates=["Date"])
    final = all_final(p)
    cut = p[final].Date.max()
    prov = p[~final].Date.nunique()
    print(f"Final through {cut.date()};  {prov} non-final weeks excluded\n")

    print("=" * 72)
    print("1. TOTAL PASS-THROUGH by lag length K   (all data -> FINAL only)")
    print("=" * 72)
    for fuel in FUELS:
        da, df_ = load(fuel, False), load(fuel, True)
        print(f"\n  {fuel}")
        print(f"    {'K':>3} {'all data':>16} {'FINAL only':>16}")
        for k in (3, 4, 6, 9, 12):
            a, ase = lag_sum(fit(da, k, ecm=False)[0])
            b, bse = lag_sum(fit(df_, k, ecm=False)[0])
            print(f"    {k:>3} {a:8.3f}+/-{ase:.3f} {b:8.3f}+/-{bse:.3f}")
        sa = [lag_sum(fit(da, k, ecm=False)[0])[0] for k in (3, 12)]
        sb = [lag_sum(fit(df_, k, ecm=False)[0])[0] for k in (3, 12)]
        print(f"    spread K=3..12:  {abs(sa[1]-sa[0]):.3f}  ->  {abs(sb[1]-sb[0]):.3f}")

    print("\n" + "=" * 72)
    print("2. ERROR CORRECTION  (weekly rate, half-life)")
    print("=" * 72)
    for fuel in FUELS:
        for lab, fo in (("all data", False), ("FINAL", True)):
            r, _ = fit(load(fuel, fo), K_MAIN)
            g = r.params["dev"]
            hl = np.log(0.5) / np.log(1 + g) if -1 < g < 0 else float("nan")
            print(f"  {fuel[:6]:7s} {lab:9s} g {g:+.4f} (t {g/r.bse['dev']:+.2f})"
                  f"  half-life {hl:.1f} wk")

    print("\n" + "=" * 72)
    print("3. SPEED BY REGIME — is pass-through faster when crude is volatile?")
    print("=" * 72)
    print("  Peer (labelling thread) reports the answer flips on Final data.")
    print("  Verified here independently, K=4, interacted, HAC.\n")
    K = 4
    for fuel in FUELS:
        for lab, fo in (("all data", False), ("FINAL", True)):
            d = load(fuel, fo)
            extra = {f"x{i}": d.d_cost.shift(i) * d.hi for i in range(K + 1)}
            extra["hi"] = d.hi
            r, fr = fit(d, K, extra=extra)
            b = np.array([r.params[f"l{i}"] for i in range(K + 1)])
            x = np.array([r.params[f"x{i}"] for i in range(K + 1)])
            ml_n = (b * np.arange(K + 1)).sum() / b.sum()
            ml_h = ((b + x) * np.arange(K + 1)).sum() / (b + x).sum()
            names = [f"x{i}" for i in range(K + 1)]
            R = np.zeros((len(names), len(r.params)))
            for j, nm in enumerate(names):
                R[j, list(r.params.index).index(nm)] = 1.0
            jp = float(r.f_test(R).pvalue)
            print(f"  {fuel[:6]:7s} {lab:9s} d_beta0 {x[0]:+.3f} "
                  f"(p {r.pvalues['x0']:.4f})  joint p {jp:.4f}   "
                  f"mean lag {ml_n:.2f} -> {ml_h:.2f} wk   n {len(fr)}")


if __name__ == "__main__":
    main()
