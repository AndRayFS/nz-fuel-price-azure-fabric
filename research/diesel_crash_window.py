"""Which weeks make diesel's pass-through depend on the lag length K?

Exploratory, 26 Nov 2026 - no rule was written before this one; the two
follow-up tests are `diesel_spread_boot.py` and `diesel_redate_crash.py`,
which were. Spec is `headline_results.py` section 1: d_net on d_cost lags
0..K plus a constant, Final weeks only, 2010+, no ECM. "Spread" is the lag
sum at K=12 minus the sum at K=3. docs/research.md, "Diesel's K-instability
is the thirteen weeks after one crash - 26 Nov 2026".

Three views:
  A  the sample ending at each week since Dec 2025 - when does the spread move?
     (also with MBIE's fuel market adjustment taken out of cost, to 11 Sep,
     the last week it can be separated)
  B  drop one equation-week at a time - which rows pull it?
  C  drop a shock window, rows t..t+12 - every equation in which week t's
     cost change is a regressor at K=12
  D  the margin's distance from its trailing 104-week mean, summed over runs
     of one sign in 2022 and 2026 - did a squeeze come back as a surplus?

    python research/diesel_crash_window.py --archive-date 2026-11-26
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "pipeline"))

import adl_decay as ad   # noqa: E402  (archive loader)

ST = ["adjusted_retail_price_status", "taxes_status", "gst_status", "ets_status",
      "importer_cost_status", "importer_margin_status"]


def load(date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The panel and margin.csv of one published archive."""
    ad.load_archive(date)
    p = pd.read_csv(ad.CACHE / "panel_weekly.csv", parse_dates=["Date"])
    with zipfile.ZipFile(ad.CACHE / f"nz-fuel-{date}.zip") as z:
        mg = pd.read_csv(io.BytesIO(z.read("margin.csv")), parse_dates=["week_date"])
    return p, mg


COMCOM_XLSX = ROOT / "data" / "comcom" / "Fuel-price-monitoring-Data-to-24-November-2026.xlsx"


def comcom_weekly(p: pd.DataFrame, xlsx=COMCOM_XLSX) -> pd.DataFrame:
    """ComCom's daily refined cost and retail price as MBIE weeks, tax-exclusive.

    Mean over MBIE's Monday-Sunday week, stamped Friday; converted as
    x / 1.15 - taxes - ets with MBIE's taxes and ETS for that week. The same
    arithmetic as diesel_comcom_dating.py (docs/mbie_notes.md, "The rebuilt
    April weeks lag ComCom's live series").
    """
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    cc = pd.DataFrame(rows[1:], columns=rows[0])
    cc["DATE"] = pd.to_datetime(cc.DATE, dayfirst=True)
    cc["fuel"] = cc.FUEL_TYPE.map({"91": "Regular Petrol", "95": "Premium Petrol 95R", "Diesel": "Diesel"})
    cc["week"] = cc.DATE - pd.to_timedelta(cc.DATE.dt.weekday, unit="D") + pd.Timedelta(days=4)
    g = cc.groupby(["fuel", "week"]).agg(cost=("REFINED_COSTS", "mean"),
                                         retail=("RETAIL_PRICES_AVG", "mean")).reset_index()
    x = g.merge(p.rename(columns={"Date": "week", "Fuel": "fuel"}), on=["fuel", "week"], how="inner")
    x["cc_cost_excl"] = x.cost / 1.15 - x.taxes - x.ets
    x["cc_retail_excl"] = x.retail / 1.15 - x.taxes - x.ets
    return x


def frame(p: pd.DataFrame, adj: pd.Series | None, fuel: str) -> pd.DataFrame:
    d = p[p.Fuel == fuel].sort_values("Date").set_index("Date").copy()
    cost = d.importer_cost - (adj.reindex(d.index).fillna(0.0) if adj is not None else 0.0)
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = cost.diff()
    d = d[d.index >= "2010-01-01"]
    ok = np.ones(len(d), bool)
    for c in ST:
        ok &= (d[c] == "Final").to_numpy()
    return d[ok]


def design(d: pd.DataFrame, K: int):
    X = np.column_stack([np.ones(len(d))] + [d.d_cost.shift(i).to_numpy() for i in range(K + 1)])
    y = d.d_net.to_numpy()
    m = ~np.isnan(X).any(1) & ~np.isnan(y)
    return X, y, m


def lagsum(d, K, drop=None):
    X, y, m = design(d, K)
    if drop is not None:
        m = m & ~drop
    b = np.linalg.lstsq(X[m], y[m], rcond=None)[0]
    return b[1:].sum(), b


def spread(d, drop=None):
    s3 = lagsum(d, 3, drop)[0]
    s12 = lagsum(d, 12, drop)[0]
    return s3, s12, s12 - s3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-26")
    ap.add_argument("--fuel", default="Diesel")
    args = ap.parse_args()
    p, mg = load(args.archive_date)
    adj = mg[mg.fuel == args.fuel].set_index("week_date").adjustment_cpl
    pd.set_option("display.width", 220)

    d = frame(p, None, args.fuel)
    print(f"{args.fuel}: Final through {d.index.max().date()}, n={len(d)}")
    base = spread(d)
    print("base  K3 %.3f  K12 %.3f  spread %.3f" % base)
    print("K path:", " ".join(f"K{k}={lagsum(d, k)[0]:.3f}" for k in range(13)))

    print("\n== A. sample ending at each week (2010+ Final through END)")
    rows = [(e.date(), *spread(d[d.index <= e])) for e in d.index[d.index >= "2025-12-26"]]
    A = pd.DataFrame(rows, columns=["end", "K3", "K12", "spread"])
    A["d_spread"] = A.spread.diff()
    dd = frame(p, adj, args.fuel)
    dd = dd[dd.index <= "2026-09-11"]
    A2 = pd.DataFrame([(e.date(), *spread(dd[dd.index <= e])) for e in dd.index[dd.index >= "2025-12-26"]],
                      columns=["end", "K3_noadj", "K12_noadj", "spread_noadj"])
    A = A.merge(A2, on="end", how="left")
    w = d[d.index >= "2025-12-26"][["d_cost", "d_net"]].reset_index()
    w["end"] = w.Date.dt.date
    A = A.merge(w[["end", "d_cost", "d_net"]], on="end")
    A["adj"] = adj.reindex(pd.to_datetime(A.end)).to_numpy()
    print(A.round(3).to_string(index=False))

    X, y, m = design(d, 12)
    idx = d.index
    print("\n== B. drop one equation-week (row) at a time: top 15 by |change in spread|")
    res = []
    for i in np.where(m)[0]:
        drop = np.zeros(len(d), bool)
        drop[i] = True
        s = spread(d, drop)
        res.append((idx[i].date(), s[2] - base[2], s[0] - base[0], s[1] - base[1],
                    d.d_cost.iloc[i], d.d_net.iloc[i]))
    B = pd.DataFrame(res, columns=["week", "d_spread", "d_K3", "d_K12", "d_cost", "d_net"])
    top = B.reindex(B.d_spread.abs().sort_values(ascending=False).index).head(15)
    print(top.round(3).to_string(index=False))
    print("share of 2026 rows in top 15:", (pd.to_datetime(top.week) >= "2026-01-01").mean())

    print("\n== C. drop a shock window: rows t..t+12")
    res = []
    for i in np.where(m)[0]:
        drop = np.zeros(len(d), bool)
        drop[i:i + 13] = True
        s = spread(d, drop)
        res.append((idx[i].date(), s[2] - base[2], s[0] - base[0], s[1] - base[1], d.d_cost.iloc[i]))
    C = pd.DataFrame(res, columns=["shock_week", "d_spread", "d_K3", "d_K12", "d_cost_that_week"])
    print(C.reindex(C.d_spread.abs().sort_values(ascending=False).index).head(12).round(3).to_string(index=False))

    print("\n== D. margin against its trailing 104-week mean, summed over runs of one sign (c/L x weeks, |sum| > 60)")
    raw = p[p.Fuel == args.fuel].sort_values("Date").set_index("Date")
    a = adj.reindex(raw.index).fillna(0.0)
    for lab, marg in (("as published", raw.importer_margin), ("without adjustment", raw.importer_margin + a)):
        gap = marg - marg.rolling(104, min_periods=104).mean().shift(1)
        for ep, (s0, s1) in {"2022": ("2022-02-01", "2022-12-31"), "2026": ("2026-02-27", "2026-09-25")}.items():
            g = gap[(gap.index >= s0) & (gap.index <= s1)]
            runs = (np.sign(g) != np.sign(g).shift()).cumsum()
            R = pd.DataFrame({"sum": g.groupby(runs).sum(), "n": g.groupby(runs).size(),
                              "start": g.groupby(runs).apply(lambda z: z.index[0].date()),
                              "end": g.groupby(runs).apply(lambda z: z.index[-1].date())})
            big = R[R["sum"].abs() > 60]
            print(f"  {lab:19s} {ep}: " + "; ".join(
                f"{r.start}..{r.end} ({int(r.n)}w) {r['sum']:+.0f}" for _, r in big.iterrows()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
