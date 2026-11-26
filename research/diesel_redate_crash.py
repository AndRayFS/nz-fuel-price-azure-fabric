"""Is diesel's 24 Apr 2026 cost crash misdated? How far must it move to stop mattering?

Written 26 Nov 2026 BEFORE the run.

MBIE suspended importer cost 18 Mar - 1 Jul 2026 and rebuilt it afterwards.
Diesel's cost fell -108.5 c/L in the week of 24 Apr (petrol -19.1, Dubai flat).
If the rebuild put that fall too early, the pump's slow fall after it is partly
a dating error. Re-date only that step, keep the cost level identical outside
the re-dated weeks, move margin by the same amount the other way, re-fit.

Variants: delay the whole step by s = 1, 2, 3 weeks; spread it evenly over
m = 2, 3, 4, 6, 8 weeks from 24 Apr. Control: spread the +61.9 rise of
6 Mar over 3 weeks (the rise was absorbed without instability, so a
re-dating that helps there too would mean the test is not diagnostic).

Rule:
  TIMING PLAUSIBLE as the main cause if some variant needing at most two
  weeks (delay 1-2, or spread 2-3) brings the no-ECM spread (K12 - K3) to
  0.15 or below.
  TIMING IMPLAUSIBLE as the main cause if only variants of four weeks or
  more do so (MBIE would have to be a month or more out).
  The control is read only as a check on the test, not scored.
"""
# First run 26 Nov 2026 as a scratch script on a panel built from that day's
# archive; moved here afterwards with only its input changed. The docstring
# above is the rule as written before that run (one code fix was made before
# it: a 3-week delay is reported as undecided, as the rule's text says, not
# scored with the four-week-and-longer variants).
#   python research/diesel_redate_crash.py --archive-date 2026-11-26
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
ST = ["adjusted_retail_price_status", "taxes_status", "gst_status", "ets_status",
      "importer_cost_status", "importer_margin_status"]
p, _ = load(ARGS.archive_date)
raw = p[p.Fuel == "Diesel"].sort_values("Date").set_index("Date")
CRASH, RISE = pd.Timestamp("2026-04-24"), pd.Timestamp("2026-03-06")
WIN = (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-24"))


def redate(at, plan):
    """plan: list of (week offset, share of the step) summing to 1."""
    cost = raw.importer_cost.copy()
    dc = cost.diff()
    i0 = cost.index.get_loc(at)
    step = dc.iloc[i0]
    dc.iloc[i0] -= step
    for off, sh in plan:
        dc.iloc[i0 + off] += step * sh
    new = cost.iloc[0] + dc.fillna(0).cumsum()
    new.iloc[0] = cost.iloc[0]
    return new


def frame(cost):
    d = raw.copy()
    shift = cost - raw.importer_cost
    d["importer_cost"] = cost
    d["importer_margin"] = raw.importer_margin - shift
    d["net"] = d.adjusted_retail_price - d.taxes - d.gst - d.ets
    d["d_net"] = d.net.diff()
    d["d_cost"] = d.importer_cost.diff()
    dev = d.importer_margin - d.importer_margin.rolling(104, min_periods=104).mean()
    d["dev1"], d["dev2"] = dev.shift(1), dev.shift(2)
    d = d[d.index >= "2010-01-01"]
    ok = np.ones(len(d), bool)
    for c in ST:
        ok &= (d[c] == "Final").to_numpy()
    return d[ok]


def sums(d, extra=(), drop_window=False):
    lags = {i: d.d_cost.shift(i).to_numpy() for i in range(13)}
    allc = np.column_stack(list(lags.values()) + [d.dev1, d.dev2, d.d_net])
    rows = ~np.isnan(allc).any(1)
    if drop_window:
        rows &= ~((d.index >= WIN[0]) & (d.index <= WIN[1]))
    y = d.d_net.to_numpy()[rows]
    out, ssr6 = [], None
    for K in range(13):
        X = np.column_stack([np.ones(len(d))] + [lags[i] for i in range(K + 1)]
                            + [d[e].to_numpy() for e in extra])[rows]
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        out.append(b[1:K + 2].sum())
        if K == 6:
            r = y - X @ b
            m26 = d.index[rows] >= "2026-03-01"
            ssr6 = (float((r ** 2).sum()), float((r[m26] ** 2).sum()))
    return np.array(out), ssr6


variants = {"as published": None}
for s in (1, 2, 3):
    variants[f"delay {s} wk"] = (CRASH, [(s, 1.0)])
for m in (2, 3, 4, 6, 8):
    variants[f"spread {m} wk"] = (CRASH, [(j, 1 / m) for j in range(m)])
variants["CONTROL rise 6 Mar spread 3"] = (RISE, [(j, 1 / 3) for j in range(3)])

rows = []
for name, v in variants.items():
    cost = raw.importer_cost if v is None else redate(*v)
    d = frame(cost)
    n0, ssr = sums(d)
    e2, _ = sums(d, ("dev1", "dev2"))
    nw, _ = sums(d, drop_window=True)
    mg = d.importer_margin.reindex([pd.Timestamp(x) for x in ("2026-04-24", "2026-05-01", "2026-05-08")])
    rows.append({
        "variant": name,
        "K3": n0[3], "K12": n0[12], "spread": n0[12] - n0[3], "range": n0[3:].max() - n0[3:].min(),
        "ECM2 spread": e2[12] - e2[3], "ECM2 range": e2[3:].max() - e2[3:].min(),
        "spread w/o window": nw[12] - nw[3],
        "SSR K6 all": ssr[0], "SSR K6 2026": ssr[1],
        "margin 24Apr/1May/8May": "/".join(f"{x:.0f}" for x in mg.to_numpy()),
    })
pd.set_option("display.width", 250)
R = pd.DataFrame(rows)
print(R.round(3).to_string(index=False))

ok_short = R[R.variant.isin(["delay 1 wk", "delay 2 wk", "spread 2 wk", "spread 3 wk"])].spread.le(0.15).any()
ok_gray = R[R.variant == "delay 3 wk"].spread.le(0.15).any()
ok_long = R[R.variant.isin(["spread 4 wk", "spread 6 wk", "spread 8 wk"])].spread.le(0.15).any()
if ok_short:
    verdict = "TIMING PLAUSIBLE"
elif ok_gray:
    verdict = "UNDECIDED (only a 3-week delay reaches 0.15; the rule does not score 3 weeks)"
elif ok_long:
    verdict = "TIMING IMPLAUSIBLE (needs >= 4 wk)"
else:
    verdict = "TIMING IMPLAUSIBLE (no variant reaches 0.15)"
print("\nRULE:", verdict)
