"""Step 8: walk-forward test. Does any of this beat "the price won't move"?

Everything is refit at every cutoff on data up to that week only. The
target is the PUMP price, not the commercial part, so the ADL has to carry
its own conversion and be charged for its errors:

    d_retail = 1.15 * (d_net + d_taxes + d_ets)

with d_ets predicted as 0 (it is a random walk — "unchanged" beats momentum
by 68%) and d_taxes as 0 (announced changes are knowable in principle, but
using them would be hindsight here). Verified exact on the 2026 crisis:
48.76 predicted against 48.7 actual for petrol, 83.55 against 83.5 diesel.

METHODS

  naive        d_retail = 0. The benchmark that matters.
  full_pass    the last h weeks of cost change arrive over the next h.
               A one-line rule with no fitting, to show what the model has
               to beat before its machinery earns its keep.
  report1_ish  Report 1's formula, `slope * (crude_t - crude_{t-k})`, with
               BOTH the lag k and the levels slope refit on a trailing
               26-week window.

               NOT "Report 1". The real measure takes k and the slope from
               the *current period*, and periods are drawn after the fact —
               that 28 Feb 2026 began a crisis was knowable only weeks
               later. A period-conditioned method cannot be honestly
               backtested at all; this is the closest thing that can.
  adl          fits d_net on d_cost lags 0..K on all data up to the cutoff.
  adl_ecm      the same, plus the margin's distance from its trailing
               104-week mean.

THE h-STEP STRUCTURE IS THE WHOLE POINT. To predict week t+j we may only
use cost changes already observed at t, i.e. lag k >= j. So the h-week
forecast uses coefficients b_k for k >= 1..h only — it is the pass-through
of moves that have ALREADY happened, which is the one thing this data can
honestly support. Longer horizons lose the early, heavy weights, so
accuracy should decay with h; if it does not, something is leaking.

K is fixed at 6 rather than reselected each week: it is the stable region
for the normal regime. This is a mild look-ahead (K was chosen on the full
sample) and is noted rather than hidden.

REGIME SPLIT IS EX POST ONLY. `crude_vol_9w` in seeds/period_flags.csv is a
CENTRED window — verified here, correlation 0.9925 against a centred
recomputation versus 0.72 trailing — so it sees four weeks ahead and must
never enter a forecast. It is used only to split the results afterwards.

WHAT THIS CANNOT FIX: MBIE revises published weeks, and the panel is the
current vintage, so "data available at t" already contains later
corrections. Every method gets that advantage equally, so the ranking
should hold; the absolute errors are flattered.

PRE-REGISTERED THRESHOLD, fixed before running: the ADL must beat naive on
MAE at h=2 in non-crisis weeks. If it does not, the model is descriptive
and will be written up as such.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PANEL = HERE / "data" / "panel_weekly.csv"
FLAGS = HERE.parent / "seeds" / "period_flags.csv"

START = "2010-01-01"       # identity does not reconcile before this
MIN_TRAIN = 156            # 3 years before the first forecast
K = 6
ECM_WINDOW = 104
HORIZONS = (1, 2, 3)
R1_WINDOW = 26             # trailing window for the Report 1-style refit
R1_MAXLAG = 8

# The training filter, stated as the list of variables the fit reads. MBIE
# publishes status per value, not per week, so "is this week final" is not
# a question the data answers — this is: are the six series the ADL
# consumes all final. `net` needs the first four, `d_cost` the fifth, `dev`
# the sixth. `dubai_crude_nzd` is absent because only report1_ish uses it
# and report1_ish is applied, never fitted, here.
TRAIN_STATUS_COLS = (
    "adjusted_retail_price_status",
    "taxes_status",
    "gst_status",
    "ets_status",
    "importer_cost_status",
    "importer_margin_status",
)


def load(fuel: str) -> pd.DataFrame:
    p = pd.read_csv(PANEL, parse_dates=["Date"])
    f = pd.read_csv(FLAGS, parse_dates=["week_date"])
    d = p[p.Fuel == fuel].merge(
        f[f.fuel == fuel], left_on="Date", right_on="week_date", how="left"
    ).sort_values("Date").set_index("Date")
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["d_retail"] = d.adjusted_retail_price.diff()
    # Train on Final only, but APPLY everywhere. Those are different things
    # and conflating them cost the report its last 19 weeks: an earlier
    # version filtered here, which silently truncated the whole series at
    # 27 Mar 2026 rather than just keeping provisional weeks out of the fit.
    #
    # Applying to provisional weeks is defensible and was checked: the
    # target (`adjusted_retail_price`) has never been revised in 1,164
    # weeks, so the forecast's base is solid, and the factor is revised by
    # ~0.5 c/L, worth ~0.6 c/L of forecast error against a model MAE of
    # 2.7. Rows carry `input_status` so the report can mark them.
    #
    # Before 22 Aug 2026 this read a single `status` column that
    # export_panel.py recovered from the snapshot with an unordered
    # `select top 1`, which on a week that had already transitioned could
    # return the superseded Provisional row. The status now comes from
    # silver, per variable, and the filter names its variables.
    d["is_final"] = np.logical_and.reduce(
        [d[c].eq("Final").to_numpy() for c in TRAIN_STATUS_COLS]
    )
    d["dev"] = (d.importer_margin
                - d.importer_margin.rolling(ECM_WINDOW, min_periods=ECM_WINDOW).mean()
                ).shift(1)
    return d[d.index >= START]


def ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def fit_adl(d: pd.DataFrame, upto: int, with_ecm: bool) -> np.ndarray | None:
    """Coefficients from rows strictly before `upto`. Returns [const, b0..bK(, g)]."""
    cols = [d.d_cost.shift(i).to_numpy() for i in range(K + 1)]
    if with_ecm:
        cols.append(d.dev.to_numpy())
    X = np.column_stack([np.ones(len(d))] + cols)[:upto]
    y = d.d_net.to_numpy()[:upto]
    # Fit on FINAL rows only — this is the filter that belongs here, rather
    # than on the whole frame.
    ok = (np.isfinite(X).all(axis=1) & np.isfinite(y)
          & d.is_final.to_numpy()[:upto])
    if ok.sum() < MIN_TRAIN:
        return None
    return ols(y[ok], X[ok])


def adl_forecast(d: pd.DataFrame, t: int, beta: np.ndarray, h: int,
                 with_ecm: bool) -> float:
    """Cumulative d_net over t+1..t+h using only cost changes known at t."""
    dc = d.d_cost.to_numpy()
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(j, K + 1):            # k < j would need unseen data
            idx = t + j - k
            if idx < 0 or not np.isfinite(dc[idx]):
                return np.nan
            step += beta[1 + k] * dc[idx]
        if with_ecm:
            dev = d.dev.to_numpy()[t]        # known at t
            if not np.isfinite(dev):
                return np.nan
            step += beta[-1] * dev
        total += step
    return total


def report1_ish(d: pd.DataFrame, t: int) -> float:
    """Refit lag and levels slope on a trailing window, then apply the formula."""
    crude = d.dubai_crude_nzd.to_numpy()
    price = d.adjusted_retail_price.to_numpy()
    lo = t - R1_WINDOW + 1
    if lo - R1_MAXLAG < 0:
        return np.nan
    best_r, best_k, best_slope = -2.0, 0, 0.0
    for k in range(R1_MAXLAG + 1):
        x, y = crude[lo - k:t + 1 - k], price[lo:t + 1]
        if len(x) != len(y) or not (np.isfinite(x).all() and np.isfinite(y).all()):
            continue
        if x.std() == 0 or y.std() == 0:
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best_r:
            best_r, best_k = r, k
            best_slope = float(np.cov(x, y, bias=True)[0, 1] / x.var())
    if best_r < -1:
        return np.nan
    if t - best_k < 0:
        return np.nan
    return best_slope * (crude[t] - crude[t - best_k])


PRICE_AT: dict = {}


def main() -> None:
    rows = []
    for fuel in ("Regular Petrol", "Diesel", "Premium Petrol 95R"):
        d = load(fuel)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        cost = d.importer_cost.to_numpy()
        hi = (d.crude_vol_regime == "high").to_numpy()
        for i, dt in enumerate(d.index):
            PRICE_AT[(fuel, dt)] = float(retail[i])

        # Run to the end of the data, not to n - max(HORIZONS). The last few
        # weeks produce a call with no outcome yet — that is the live part of
        # the report and the reason it exists.
        is_final = d.is_final.to_numpy()
        for t in range(MIN_TRAIN, n):
            b_adl = fit_adl(d, t + 1, with_ecm=False)
            b_ecm = fit_adl(d, t + 1, with_ecm=True)
            if b_adl is None:
                continue
            r1 = report1_ish(d, t)
            for h in HORIZONS:
                actual = (retail[t + h] - retail[t]) if t + h < n else np.nan
                fp = (cost[t] - cost[t - h]) * 1.15 if t - h >= 0 else np.nan
                a = adl_forecast(d, t, b_adl, h, False)
                e = (adl_forecast(d, t, b_ecm, h, True)
                     if b_ecm is not None else np.nan)
                rows.append(dict(
                    fuel=fuel, date=d.index[t], h=h, actual=actual, hi=hi[t],
                    input_status="final" if is_final[t] else "provisional",
                    outcome_known=bool(np.isfinite(actual)),
                    naive=0.0, full_pass=fp, report1_ish=r1,
                    adl=a * 1.15 if np.isfinite(a) else np.nan,
                    adl_ecm=e * 1.15 if np.isfinite(e) else np.nan,
                ))

    res = pd.DataFrame(rows)
    res.to_csv(HERE / "data" / "backtest_results.csv", index=False)

    # Seed for Report 1: one row per (week, fuel, horizon) carrying the price
    # level the model would have called at that week, beside what happened.
    # Levels rather than changes because a reader reads a price, not a delta.
    seed = res.rename(columns={"date": "week_date"}).copy()
    seed["price_now"] = seed.apply(
        lambda r: PRICE_AT[(r.fuel, r.week_date)], axis=1)
    seed["actual_price"] = seed.price_now + seed.actual
    for m in ("naive", "adl", "adl_ecm", "report1_ish", "full_pass"):
        seed[f"pred_{m}"] = seed.price_now + seed[m]
        seed[f"err_{m}"] = seed[f"pred_{m}"] - seed.actual_price
    seed["target_week"] = seed.week_date + pd.to_timedelta(seed.h * 7, unit="D")
    keep = (["week_date", "target_week", "fuel", "h", "input_status",
             "outcome_known", "price_now", "actual_price"]
            + [f"pred_{m}" for m in ("naive", "adl", "adl_ecm", "report1_ish")]
            + [f"err_{m}" for m in ("naive", "adl", "adl_ecm", "report1_ish")])
    out = HERE.parent / "seeds" / "forecast_history.csv"
    seed[keep].round(4).to_csv(out, index=False)
    print(f"{len(seed)} rows -> {out}")
    methods = ["naive", "full_pass", "report1_ish", "adl", "adl_ecm"]

    # Accuracy tables only over weeks whose outcome is known. The most
    # recent rows are calls without an outcome yet - the live part of the
    # report - and averaging them in would silently drop them anyway.
    ev = res[res.outcome_known]
    for fuel in ev.fuel.unique():
        for label, sub in (("ALL", ev[ev.fuel == fuel]),
                           ("non-crisis", ev[(ev.fuel == fuel) & ~ev.hi]),
                           ("crisis", ev[(ev.fuel == fuel) & ev.hi])):
            print(f"\n{fuel} — {label}")
            print(f"  {'h':>2} {'n':>5} " + "".join(f"{m:>13}" for m in methods))
            for h in HORIZONS:
                s = sub[sub.h == h].dropna(subset=methods)
                if s.empty:
                    continue
                maes = [np.abs(s[m] - s.actual).mean() for m in methods]
                line = f"  {h:>2} {len(s):>5} " + "".join(f"{v:>13.3f}" for v in maes)
                print(line)
            s2 = sub[sub.h == 2].dropna(subset=methods)
            if not s2.empty:
                base = np.abs(s2.naive - s2.actual)
                for m in methods[1:]:
                    win = (np.abs(s2[m] - s2.actual) < base).mean()
                    print(f"     h=2 {m:>12} beats naive in {100 * win:5.1f}% of weeks")


if __name__ == "__main__":
    main()
