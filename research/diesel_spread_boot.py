"""Does the two-margin-lag ECM remove diesel's dependence on K? Robustness.

Written 26 Nov 2026 BEFORE the run. Rule:

  spread = sum of cost weights at K=12 minus at K=3 (same rows for both).
  Specs: noECM (headline section 1), ECM1 (dev t-1), ECM2 (dev t-1, t-2).
  Moving block bootstrap of regression rows, block 12 weeks, 2000 reps,
  seed 20261126, 95% percentile intervals, paired across specs.

  PASS for diesel needs all three:
    R1  full Final sample: CI of (spread_noECM - spread_ECM2) entirely > 0
    R2  full Final sample: CI of spread_ECM2 inside [-0.15, +0.15]
    R3  sample to 31 Dec 2025: |spread_ECM2| <= 0.15 (point)
  Petrol is reported beside it, with no rule.
  Block 8 and 26 are printed as a sensitivity check only.
"""
# First run 26 Nov 2026 as a scratch script on a panel built from that day's
# archive; moved here afterwards with only its input changed. The docstring
# above is the rule as written before that run.
#   python research/diesel_spread_boot.py --archive-date 2026-11-26
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from diesel_crash_window import load   # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--archive-date", default="2026-11-26")
ARGS = _ap.parse_args()
REPS, SEED, BLOCK = 2000, 20261126, 12
ST = ["adjusted_retail_price_status", "taxes_status", "gst_status", "ets_status",
      "importer_cost_status", "importer_margin_status"]
SPECS = {"noECM": (), "ECM1": ("dev1",), "ECM2": ("dev1", "dev2")}
p, _ = load(ARGS.archive_date)


def prep(fuel, end):
    d = p[p.Fuel == fuel].sort_values("Date").set_index("Date")
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    dev = d.importer_margin - d.importer_margin.rolling(104, min_periods=104).mean()
    d["dev1"], d["dev2"] = dev.shift(1), dev.shift(2)
    d = d[(d.index >= "2010-01-01") & (d.index <= end)]
    ok = np.ones(len(d), bool)
    for c in ST:
        ok &= (d[c] == "Final").to_numpy()
    d = d[ok]
    lags = {i: d.d_cost.shift(i).to_numpy() for i in range(13)}
    rows = ~np.isnan(np.column_stack(list(lags.values()) + [d.dev1, d.dev2, d.d_net])).any(1)
    return d, lags, rows


def X_of(d, lags, K, extra):
    return np.column_stack([np.ones(len(d))] + [lags[i] for i in range(K + 1)]
                           + [d[e].to_numpy() for e in extra])


def spreads(d, lags, idx):
    y = d.d_net.to_numpy()[idx]
    out = {}
    for name, extra in SPECS.items():
        s = []
        for K in (3, 12):
            X = X_of(d, lags, K, extra)[idx]
            b = np.linalg.lstsq(X, y, rcond=None)[0]
            s.append(b[1:K + 2].sum())
        out[name] = (s[0], s[1], s[1] - s[0])
    return out


def boot(d, lags, rows, block, reps=REPS):
    base = np.where(rows)[0]
    n = len(base)
    k = int(np.ceil(n / block))
    rng = np.random.default_rng(SEED)
    starts = rng.integers(0, n - block + 1, size=(reps, k))
    pos = (starts[:, :, None] + np.arange(block)).reshape(reps, -1)[:, :n]
    res = {s: [] for s in SPECS}
    for r in range(reps):
        o = spreads(d, lags, base[pos[r]])
        for s in SPECS:
            res[s].append(o[s][2])
    return {s: np.array(v) for s, v in res.items()}


def ci(a):
    return np.quantile(a, [0.025, 0.975])


verdict = {}
for fuel in ("Diesel", "Regular Petrol"):
    for lab, end in (("full Final", "2026-12-31"), ("to 2025", "2025-12-31")):
        d, lags, rows = prep(fuel, end)
        pt = spreads(d, lags, np.where(rows)[0])
        print(f"\n== {fuel}, {lab}: through {d.index[rows].max().date()}, n={rows.sum()}")
        for s in SPECS:
            print(f"   {s:6s} K3 {pt[s][0]:.3f}  K12 {pt[s][1]:.3f}  spread {pt[s][2]:+.3f}")
        path = []
        for s, extra in SPECS.items():
            vals = []
            for K in range(0, 13):
                X = X_of(d, lags, K, extra)[rows]
                b = np.linalg.lstsq(X, d.d_net.to_numpy()[rows], rcond=None)[0]
                vals.append(b[1:K + 2].sum())
            path.append(f"   {s:6s} K0..12: " + " ".join(f"{v:.2f}" for v in vals))
        print("\n".join(path))
        B = boot(d, lags, rows, BLOCK)
        for s in SPECS:
            lo, hi = ci(B[s])
            print(f"   boot{BLOCK} {s:6s} spread CI [{lo:+.3f}, {hi:+.3f}]")
        diff = B["noECM"] - B["ECM2"]
        dlo, dhi = ci(diff)
        print(f"   boot{BLOCK} noECM-ECM2   point {pt['noECM'][2]-pt['ECM2'][2]:+.3f}  CI [{dlo:+.3f}, {dhi:+.3f}]")
        if lab == "full Final":
            for bl in (8, 26):
                Bb = boot(d, lags, rows, bl, reps=1000)
                print(f"   sens block {bl:2d}: ECM2 CI [{ci(Bb['ECM2'])[0]:+.3f}, {ci(Bb['ECM2'])[1]:+.3f}]"
                      f"  noECM-ECM2 CI [{ci(Bb['noECM']-Bb['ECM2'])[0]:+.3f}, {ci(Bb['noECM']-Bb['ECM2'])[1]:+.3f}]")
            # the post-crash window dropped
            keep = rows.copy()
            keep &= ~((d.index >= "2026-05-01") & (d.index <= "2026-07-24"))
            o = spreads(d, lags, np.where(keep)[0])
            print("   without 1 May-24 Jul 2026: " + "  ".join(f"{s} {o[s][2]:+.3f}" for s in SPECS))
        if fuel == "Diesel":
            if lab == "full Final":
                verdict["R1"] = dlo > 0
                lo, hi = ci(B["ECM2"])
                verdict["R2"] = (lo >= -0.15) and (hi <= 0.15)
            else:
                verdict["R3"] = abs(pt["ECM2"][2]) <= 0.15

print("\nRULE (diesel):", {k: bool(v) for k, v in verdict.items()},
      "=>", "PASS" if all(verdict.values()) else "FAIL")
