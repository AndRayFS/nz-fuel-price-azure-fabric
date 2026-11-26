"""Was diesel's slow margin closing after the April 2026 crash unusual - against
diesel's own history, and against petrol in the same weeks?

Written 26 Nov 2026 BEFORE the run. Seen before writing: the 2026 diesel gap
path (margin +60..+120% above its norm from 24 Apr to late June, closing in
early July) and the ECM half-lives on 2010+ Final data (diesel 3.8, petrol 6.3
weeks). Not seen: any earlier episode, any simulated path.

Episodes. Per fuel, from 2012 (the norm needs two clean years after 2010). One
starts in the first week the gap - (margin - norm) / norm, norm being the mean
of the 104 weeks before (margin.csv's definition) - is +30% or more, and ends in
the first later week below +15%.

Own rule. d_net on a constant, d_cost lags 0..6 and dev(t-1), the margin's
distance from its 104-week mean (headline_results.py's ECM). OLS on Final
weeks 2010-2025, per fuel. For each 2012-2025 episode the fit leaves out the 52
weeks around its start (start-26 .. start+25); for 2026 it uses all of
2010-2025.

Simulation. From the episode's first week s, net is carried forward with the
fitted rule on the actual cost changes. The dev it feeds back is the actual dev
shifted by (simulated - actual) net, with the norm held at its actual value.
Excess = actual net - simulated net, c/L, averaged over weeks s .. s+11.

Rule:
  UNUSUAL: diesel's 2026 episode (MBIE data as published) has a 12-week mean
    excess above that of every diesel episode 2012-2025.
  DIESEL-SPECIFIC: in addition, over the 2012-2025 windows of both fuels'
    episodes, the median of (diesel excess - petrol excess, same window) is
    0 or below, while in the 2026 diesel window it is above 0.
  Reported, not scored: ComCom's dating of 3-17 Apr 2026 for both fuels,
  excess as % of the norm, thresholds 20% and 40%.
"""
# First run 26 Nov 2026 as a scratch script on a panel built from that day's
# archive; moved here afterwards with only its input changed. The docstring
# above is the rule as written before that run.
#   python research/diesel_margin_episodes.py --archive-date 2026-11-26
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from diesel_crash_window import COMCOM_XLSX, comcom_weekly, load   # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--archive-date", default="2026-11-26")
_ap.add_argument("--xlsx", default=str(COMCOM_XLSX))
ARGS = _ap.parse_args()
ST = ["adjusted_retail_price_status", "taxes_status", "gst_status", "ets_status",
      "importer_cost_status", "importer_margin_status"]
FUELS = ("Diesel", "Regular Petrol")
K, H = 6, 12
p, _ = load(ARGS.archive_date)
ccw = comcom_weekly(p, ARGS.xlsx)


def series(fuel, comcom=False):
    d = p[p.Fuel == fuel].sort_values("Date").set_index("Date").copy()
    if comcom:
        cc = ccw[ccw.fuel == fuel].set_index("week").cc_cost_excl
        for w in pd.to_datetime(["2026-04-03", "2026-04-10", "2026-04-17"]):
            shift = cc[w] - d.loc[w, "importer_cost"]
            d.loc[w, "importer_cost"] += shift
            d.loc[w, "importer_margin"] -= shift
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["dev"] = (d.importer_margin - d.importer_margin.rolling(104, min_periods=104).mean()).shift(1)
    norm = d.importer_margin.rolling(104, min_periods=104).mean().shift(1)
    d["norm"] = norm
    d["gap_pct"] = (d.importer_margin - norm) / norm * 100
    ok = np.ones(len(d), bool)
    for c in ST:
        ok &= (d[c] == "Final").to_numpy()
    d["final"] = ok
    return d


def episodes(d, thr):
    g = d.gap_pct[(d.index >= "2012-01-01") & d.final]
    out, start = [], None
    for t, v in g.items():
        if start is None and v >= thr:
            start, peak = t, v
        elif start is not None:
            peak = max(peak, v)
            if v < thr / 2:
                out.append((start, t, peak))
                start = None
    if start is not None:
        out.append((start, None, peak))
    return out


def fit(d, exclude=None):
    lags = np.column_stack([d.d_cost.shift(i).to_numpy() for i in range(K + 1)])
    X = np.column_stack([np.ones(len(d)), lags, d.dev.to_numpy()])
    y = d.d_net.to_numpy()
    m = ~np.isnan(X).any(1) & ~np.isnan(y) & d.final.to_numpy() \
        & (d.index >= "2010-01-01") & (d.index < "2026-01-01")
    if exclude is not None:
        m &= ~((d.index >= exclude[0]) & (d.index <= exclude[1]))
    return np.linalg.lstsq(X[m], y[m], rcond=None)[0]


def excess(d, s, b):
    i0 = d.index.get_loc(s)
    if i0 + H > len(d):
        return np.nan, np.nan
    net = d.net.to_numpy(); dc = d.d_cost.to_numpy(); dev = d.dev.to_numpy()
    sim = net.copy()
    for i in range(i0, i0 + H):
        dev_sim = dev[i] + (sim[i - 1] - net[i - 1])
        pred = b[0] + sum(b[1 + k] * dc[i - k] for k in range(K + 1)) + b[K + 2] * dev_sim
        sim[i] = sim[i - 1] + pred
    e = net[i0:i0 + H] - sim[i0:i0 + H]
    return float(e.mean()), float(e.mean() / d.norm.iloc[i0] * 100)


def run(thr, comcom):
    D = {f: series(f, comcom) for f in FUELS}
    rows = []
    for f in FUELS:
        for s, e, peak in episodes(D[f], thr):
            y2026 = s >= pd.Timestamp("2026-01-01")
            excl = None if y2026 else (s - pd.Timedelta(weeks=26), s + pd.Timedelta(weeks=25))
            r = {"fuel": f, "start": s.date(), "end": e.date() if e is not None else None,
                 "weeks": int(((e or D[f].index.max()) - s).days / 7), "peak_gap%": round(peak),
                 "era": "import" if s >= pd.Timestamp("2022-04-01") else "refinery"}
            for g in FUELS:
                b = fit(D[g], excl)
                ex, expct = excess(D[g], s, b) if s in D[g].index else (np.nan, np.nan)
                tag = "D" if g == "Diesel" else "P"
                r[f"exc_{tag}"] = round(ex, 1)
                r[f"exc%_{tag}"] = round(expct, 1)
            rows.append(r)
    R = pd.DataFrame(rows)
    R["D-P"] = R.exc_D - R.exc_P
    return R


pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)
for thr, comcom in ((30, False), (30, True), (20, False), (40, False)):
    R = run(thr, comcom)
    print(f"\n== threshold {thr}%, {'ComCom dating 3-17 Apr 2026' if comcom else 'MBIE as published'}")
    print(R.to_string(index=False))
    if thr == 30 and not comcom:
        hist = R[pd.to_datetime(R.start) < "2026-01-01"]
        d26 = R[(R.fuel == "Diesel") & (pd.to_datetime(R.start) >= "2026-01-01")]
        dh = hist[hist.fuel == "Diesel"]
        unusual = bool(len(d26)) and bool((d26.exc_D.iloc[0] > dh.exc_D).all())
        med = float(hist["D-P"].median())
        specific = unusual and med <= 0 and float(d26["D-P"].iloc[0]) > 0
        print(f"\nRULE: diesel 2026 excess {d26.exc_D.iloc[0]:.1f} vs max of {len(dh)} earlier diesel episodes "
              f"{dh.exc_D.max():.1f} -> {'UNUSUAL' if unusual else 'not unusual'}; "
              f"median(D-P) in earlier windows {med:+.1f}, 2026 window {float(d26['D-P'].iloc[0]):+.1f} "
              f"-> {'DIESEL-SPECIFIC' if specific else 'not diesel-specific'}")
