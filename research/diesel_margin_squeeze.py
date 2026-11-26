"""Did diesel smooth the whole 2026 spike, or hold margin only on the way down?

Written 26 Nov 2026 BEFORE the run. Seen before writing: margin_episodes.py
(post-crash diesel excess +32.6 c/L a week over 12 weeks from 24 Apr = +391
c/L-weeks; petrol 0.0 in the same weeks) and ComCom's revised daily spread
(diesel: March -32, May 94, June 101 against 55 before the conflict;
cumulative since 28 Feb back to about normal by July). Not seen: any simulated
path for the squeeze.

Squeeze window, per fuel: from the first 2026 week with the margin gap at -30%
or below to the last week before the gap is back at 0 or above (MBIE data as
published). Same own rule and simulation as margin_episodes.py (K=6 plus
dev(t-1), fitted on Final 2010-2025), started at the squeeze's first week.
Sum of (actual - simulated net) over the squeeze weeks, c/L-weeks.

Rule, diesel:
  SYMMETRIC (the spike smoothed both ways): the squeeze sum is negative and
    at least half the size of the post-crash sum, i.e. -196 or below.
  ASYMMETRIC (margin held on the way down only): the squeeze sum is above -196.
Petrol is reported beside it, unscored. Also reported: ComCom's dating of
3-17 Apr for both fuels.
"""
# First run 26 Nov 2026 as a scratch script on a panel built from that day's
# archive; moved here afterwards with only its input changed. The docstring
# above is the rule as written before that run.
#   python research/diesel_margin_squeeze.py --archive-date 2026-11-26
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
K = 6
POST = {"Diesel": ("2026-04-24", 12), "Regular Petrol": ("2026-04-24", 12)}
p, _ = load(ARGS.archive_date)
ccw = comcom_weekly(p, ARGS.xlsx)


def series(fuel, comcom=False):
    d = p[p.Fuel == fuel].sort_values("Date").set_index("Date").copy()
    if comcom:
        cc = ccw[ccw.fuel == fuel].set_index("week").cc_cost_excl
        for w in pd.to_datetime(["2026-04-03", "2026-04-10", "2026-04-17"]):
            s = cc[w] - d.loc[w, "importer_cost"]
            d.loc[w, "importer_cost"] += s
            d.loc[w, "importer_margin"] -= s
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    d["dev"] = (d.importer_margin - d.importer_margin.rolling(104, min_periods=104).mean()).shift(1)
    norm = d.importer_margin.rolling(104, min_periods=104).mean().shift(1)
    d["gap_pct"] = (d.importer_margin - norm) / norm * 100
    ok = np.ones(len(d), bool)
    for c in ST:
        ok &= (d[c] == "Final").to_numpy()
    d["final"] = ok
    return d


def fit(d):
    X = np.column_stack([np.ones(len(d))] + [d.d_cost.shift(i).to_numpy() for i in range(K + 1)] + [d.dev.to_numpy()])
    y = d.d_net.to_numpy()
    m = ~np.isnan(X).any(1) & ~np.isnan(y) & d.final.to_numpy() & (d.index >= "2010-01-01") & (d.index < "2026-01-01")
    return np.linalg.lstsq(X[m], y[m], rcond=None)[0]


def path_excess(d, b, s, n):
    i0 = d.index.get_loc(pd.Timestamp(s))
    net = d.net.to_numpy(); dc = d.d_cost.to_numpy(); dev = d.dev.to_numpy()
    sim = net.copy()
    for i in range(i0, i0 + n):
        pred = b[0] + sum(b[1 + k] * dc[i - k] for k in range(K + 1)) + b[K + 2] * (dev[i] + sim[i - 1] - net[i - 1])
        sim[i] = sim[i - 1] + pred
    return net[i0:i0 + n] - sim[i0:i0 + n]


for comcom in (False, True):
    print(f"\n== {'ComCom dating 3-17 Apr' if comcom else 'MBIE as published'}")
    for f in ("Diesel", "Regular Petrol"):
        d = series(f, comcom); b = fit(d)
        g = d.gap_pct[d.index >= "2026-01-01"]
        s0 = g[g <= -30].index.min()
        after = g[(g.index > s0) & (g >= 0)].index.min()
        n = int(((after - s0).days) / 7)
        sq = path_excess(d, b, s0, n)
        post_s = d.gap_pct[(d.index > after) | (d.index == after)]
        ps = post_s[post_s >= 30].index.min()
        po = path_excess(d, b, ps, 12)
        print(f"  {f:15s} squeeze {s0.date()}..{(after - pd.Timedelta(weeks=1)).date()} ({n} wk): sum {sq.sum():+.0f}, "
              f"weekly {' '.join(f'{v:+.0f}' for v in sq)}")
        print(f"  {'':15s} surplus from {ps.date()} (12 wk): sum {po.sum():+.0f}; squeeze/surplus {-sq.sum() / po.sum():.2f}")
        if f == "Diesel" and not comcom:
            verdict = "SYMMETRIC" if sq.sum() <= -196 else "ASYMMETRIC"
            print(f"  RULE (diesel, MBIE): squeeze sum {sq.sum():+.0f} vs threshold -196 -> {verdict}")
