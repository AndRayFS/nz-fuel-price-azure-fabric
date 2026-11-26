"""Does the K-instability survive ComCom's dating of the April 2026 crash?

Written 26 Nov 2026 BEFORE the run. Seen before writing: ComCom's weekly
mean diesel cost (tax-exclusive) differs from MBIE's published importer
cost by under 7 c/L every week Feb-Jul 2026 except 3 Apr (-17.4),
10 Apr (+34.5) and 17 Apr (+85.1). Not seen: any spread under these costs.

Variant A (primary): MBIE's diesel importer cost with only those three
  weeks replaced by ComCom's; margin moved by the same amount the other way.
Variant B: every week from 6 Mar to 31 Jul 2026 replaced by ComCom's.

Rule:
  If under variant A the no-ECM spread (K12 - K3, Final 2010+) is 0.15 or
  below, MBIE's dating is the main cause of the K-instability.
  If it stays above 0.15, the instability is the pump's own slow fall after
  the crash, and the dating moves only when that fall starts.
  Variant B, ECM2 and the drop-the-window check are reported, not scored.
"""
# First run 26 Nov 2026 as two scratch scripts (the weekly ComCom table, then
# the test above); merged here afterwards with only their inputs changed.
# docs/research.md, "Diesel's K-instability is the thirteen weeks after one
# crash"; docs/mbie_notes.md, "The rebuilt April weeks lag ComCom's live series".
#
# ComCom's file: "Fuel price monitoring - Data to <date>" on
# https://www.comcom.govt.nz/regulated-industries/fuel/quarterly-monitoring-reports/
# Daily REFINED_COSTS and RETAIL_PRICES_AVG, c/L including GST, ETS and excise,
# from 1 Feb 2026. Converted here to MBIE's tax-exclusive basis as
# x / 1.15 - taxes - ets, with MBIE's own taxes and ETS for the week.
#
#   python research/diesel_comcom_dating.py --archive-date 2026-11-26 \
#       --xlsx data/comcom/Fuel-price-monitoring-Data-to-24-November-2026.xlsx
import argparse
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from diesel_crash_window import ROOT, load   # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--archive-date", default="2026-11-26")
_ap.add_argument("--xlsx", default=str(ROOT / "data" / "comcom"
                                       / "Fuel-price-monitoring-Data-to-24-November-2026.xlsx"))
ARGS = _ap.parse_args()

ST = ["adjusted_retail_price_status", "taxes_status", "gst_status", "ets_status",
      "importer_cost_status", "importer_margin_status"]
WIN = (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-24"))
p, mg = load(ARGS.archive_date)


def comcom_weekly() -> pd.DataFrame:
    wb = openpyxl.load_workbook(ARGS.xlsx, read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    cc = pd.DataFrame(rows[1:], columns=rows[0])
    cc["DATE"] = pd.to_datetime(cc.DATE, dayfirst=True)
    cc["fuel"] = cc.FUEL_TYPE.map({"91": "Regular Petrol", "95": "Premium Petrol 95R", "Diesel": "Diesel"})
    # MBIE's week runs Monday to Sunday and is stamped with its Friday
    cc["week"] = cc.DATE - pd.to_timedelta(cc.DATE.dt.weekday, unit="D") + pd.Timedelta(days=4)
    g = cc.groupby(["fuel", "week"]).agg(cost=("REFINED_COSTS", "mean"), retail=("RETAIL_PRICES_AVG", "mean"),
                                         days=("DATE", "count")).reset_index()
    m = p.rename(columns={"Date": "week", "Fuel": "fuel"}).merge(
        mg.rename(columns={"week_date": "week"})[["week", "fuel", "adjustment_cpl"]], on=["week", "fuel"], how="left")
    x = g.merge(m, on=["fuel", "week"], how="inner")
    x["cc_cost_excl"] = x.cost / 1.15 - x.taxes - x.ets
    x["cc_retail_excl"] = x.retail / 1.15 - x.taxes - x.ets
    x["gap_pub"] = x.importer_cost - x.cc_cost_excl
    return x


ccw = comcom_weekly()
pd.set_option("display.width", 250)
print("== ComCom against MBIE's published importer cost, c/L tax-exclusive")
for f in ("Diesel", "Regular Petrol"):
    z = ccw[ccw.fuel == f].sort_values("week").copy()
    z["d_cc"], z["d_mbie"] = z.cc_cost_excl.diff(), z.importer_cost.diff()
    out = (z.week < "2026-04-03") | (z.week > "2026-05-01")
    other = z[(z.week >= "2026-02-06") & (z.week <= "2026-07-31") & ~z.week.between("2026-04-03", "2026-04-17")]
    print(f"\n  {f}: max |gap| outside 3-17 Apr, Feb-Jul: {other.gap_pub.abs().max():.1f}; corr of weekly changes "
          f"all {z.d_cc.corr(z.d_mbie):.3f}, outside 3 Apr-1 May {z[out].d_cc.corr(z[out].d_mbie):.3f}")
    t = z[(z.week >= "2026-03-27") & (z.week <= "2026-05-01")][["week", "days", "cc_cost_excl", "importer_cost",
                                                                  "gap_pub", "d_cc", "d_mbie", "cc_retail_excl"]]
    print(t.assign(week=t.week.dt.date).round(1).to_string(index=False))
    a, b = z.set_index("week").cc_cost_excl, z.set_index("week").importer_cost
    print(f"  fall 3 Apr -> 24 Apr: ComCom {a['2026-04-24'] - a['2026-04-03']:+.1f}, MBIE {b['2026-04-24'] - b['2026-04-03']:+.1f}")

raw = p[p.Fuel == "Diesel"].sort_values("Date").set_index("Date")
cc = ccw[ccw.fuel == "Diesel"].set_index("week").cc_cost_excl


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


def sums(d, extra=(), drop_window=False, end=None):
    lags = {i: d.d_cost.shift(i).to_numpy() for i in range(13)}
    rows = ~np.isnan(np.column_stack(list(lags.values()) + [d.dev1, d.dev2, d.d_net])).any(1)
    if drop_window:
        rows &= ~((d.index >= WIN[0]) & (d.index <= WIN[1]))
    if end is not None:
        rows &= d.index <= end
    y = d.d_net.to_numpy()[rows]
    out = []
    for K in range(13):
        X = np.column_stack([np.ones(len(d))] + [lags[i] for i in range(K + 1)]
                            + [d[e].to_numpy() for e in extra])[rows]
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        out.append(b[1:K + 2].sum())
    return np.array(out)


costs = {"as published": raw.importer_cost.copy()}
a = raw.importer_cost.copy()
for w in ("2026-04-03", "2026-04-10", "2026-04-17"):
    a[pd.Timestamp(w)] = cc[pd.Timestamp(w)]
costs["A: ComCom 3-17 Apr"] = a
b = raw.importer_cost.copy()
for w in cc.index[(cc.index >= "2026-03-06") & (cc.index <= "2026-07-31")]:
    if w in b.index:
        b[w] = cc[w]
costs["B: ComCom 6 Mar-31 Jul"] = b

print("\n== The test")
res = []
for name, cost in costs.items():
    d = frame(cost)
    n0 = sums(d); e2 = sums(d, ("dev1", "dev2")); nw = sums(d, drop_window=True)
    m = d.importer_margin.reindex(pd.to_datetime(["2026-04-03", "2026-04-10", "2026-04-17", "2026-04-24"]))
    res.append({"variant": name, "K3": n0[3], "K12": n0[12], "spread": n0[12] - n0[3],
                "range": n0[3:].max() - n0[3:].min(), "ECM2 spread": e2[12] - e2[3],
                "ECM2 range": e2[3:].max() - e2[3:].min(), "spread w/o window": nw[12] - nw[3],
                "margin 3/10/17/24 Apr": "/".join(f"{v:.0f}" for v in m.to_numpy())})
    if name.startswith("A"):
        path = []
        for e in ("2026-03-27", "2026-04-03", "2026-04-10", "2026-04-17", "2026-04-24", "2026-05-01",
                  "2026-05-08", "2026-05-15", "2026-06-26", "2026-07-17", "2026-09-25"):
            s = sums(d, end=pd.Timestamp(e)); path.append(f"{e[5:]} {s[12]-s[3]:+.3f}")
        print("A, spread with the sample ending at:", "  ".join(path))
        print("A, no-ECM K0..12:", " ".join(f"{v:.2f}" for v in n0))
        print("A, ECM2   K0..12:", " ".join(f"{v:.2f}" for v in e2))
print(pd.DataFrame(res).round(3).to_string(index=False))
sA = res[1]["spread"]
print("\nRULE:", "MBIE dating is the main cause" if sA <= 0.15 else
      "instability survives ComCom's dating: it is the pump's own slow fall")
