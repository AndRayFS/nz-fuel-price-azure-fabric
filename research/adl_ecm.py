"""Step 5: add an error-correction term to the distributed lag.

The baseline models only *changes*, so it has no way to express the pull
back toward a normal markup. That pull is real and was watched happening:
diesel's margin hit an all-time low of -12.4 c/L on 13 Mar 2026 and then
recovered while costs were falling. A changes-only model sees price rising
without cost rising and books it as noise.

    d_net_t = a + sum_k b_k d_cost_{t-k} + g * dev_{t-1} + e_t

where `dev` is the margin's distance from its own recent normal:

    dev_t = importer_margin_t - trailing mean over W weeks

The trailing mean, not the full-history mean: margin levels have tripled
since 2004, so a fixed centre would measure inflation in unmodelled
downstream costs (docs/mbie_notes.md). W is varied here rather than
assumed. The mean is computed on the FULL history and only then trimmed to
the import era, so no window is built from data the model would not have
had.

Expected sign is g < 0 — margin above normal means the next move is
smaller than the cost move alone implies. From g, the weekly correction
rate, comes a half-life: ln(0.5)/ln(1+g) weeks to close half the gap.

PRE-REGISTERED PREDICTION, stated before running: diesel's total
pass-through creeps upward with lag length (0.833 at K=3 to 1.213 at
K=12) while petrol's does not. If that creep is the model expressing
error correction the only way it can — by recruiting ever more cost lags —
then an explicit `dev` term should flatten it. If the creep survives, the
explanation is something else and this hypothesis dies like the
seasonality one.

CAVEAT that must travel with any g reported here. `dev` contains
net_{t-1} - cost_{t-1}, and the dependent variable contains -net_{t-1}.
The two share a term with opposite signs, so measurement error in the
price level alone produces a negative g. This is the standard ECM
specification and the standard objection to it; treat the *sign* as weak
evidence and judge the term instead on whether it does what was predicted
above.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).parent))
from adl_baseline import PANEL, IMPORT_ERA, FUELS  # noqa: E402

WINDOWS = [52, 78, 104]


def build_ecm(fuel: str, window: int) -> pd.DataFrame:
    df = pd.read_csv(PANEL, parse_dates=["Date"])
    d = df[df.Fuel == fuel].sort_values("Date").set_index("Date").copy()
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    normal = d.importer_margin.rolling(window, min_periods=window).mean()
    d["dev"] = (d.importer_margin - normal).shift(1)
    return d[d.index >= IMPORT_ERA]


def fit(d: pd.DataFrame, k: int, with_ecm: bool):
    cols = {f"lag{i}": d.d_cost.shift(i) for i in range(k + 1)}
    if with_ecm:
        cols["dev"] = d.dev
    X = pd.DataFrame(cols)
    frame = pd.concat([d.d_net, X], axis=1).dropna()
    res = sm.OLS(frame.d_net, sm.add_constant(frame.drop(columns="d_net"))).fit(
        cov_type="HAC", cov_kwds={"maxlags": k + 2}
    )
    c = np.array([1.0 if p.startswith("lag") else 0.0 for p in res.params.index])
    total = float(c @ res.params)
    se = float(np.sqrt(c @ res.cov_params() @ c))
    return res, total, se


def main() -> None:
    for fuel in FUELS:
        print(f"\n{'=' * 70}\n{fuel}\n{'=' * 70}")
        for window in WINDOWS:
            d = build_ecm(fuel, window)
            res, _, _ = fit(d, 6, with_ecm=True)
            g = res.params["dev"]
            t = g / res.bse["dev"]
            hl = np.log(0.5) / np.log(1 + g) if -1 < g < 0 else float("nan")
            print(f"\n  W={window:3d} weeks:  g = {g:+.4f}  (HAC t {t:+.2f}, "
                  f"p {res.pvalues['dev']:.4f}),  half-life {hl:.1f} weeks")

        # Does it flatten the creep? Same window for all K.
        d = build_ecm(fuel, 104)
        print(f"\n  total pass-through by K, W=104:")
        print(f"  {'K':>3} {'no ECM':>16} {'with ECM':>16} {'g':>9}")
        for k in (3, 4, 6, 8, 9, 12):
            _, a, ase = fit(d, k, False)
            r, b, bse = fit(d, k, True)
            print(f"  {k:>3} {a:8.3f}+/-{ase:.3f} {b:8.3f}+/-{bse:.3f} "
                  f"{r.params['dev']:+9.4f}")
        spread_no = max(fit(d, k, False)[1] for k in (3, 12)) - min(
            fit(d, k, False)[1] for k in (3, 12))
        spread_yes = max(fit(d, k, True)[1] for k in (3, 12)) - min(
            fit(d, k, True)[1] for k in (3, 12))
        print(f"  spread K=3 to K=12:  {spread_no:.3f} -> {spread_yes:.3f}")


if __name__ == "__main__":
    main()
