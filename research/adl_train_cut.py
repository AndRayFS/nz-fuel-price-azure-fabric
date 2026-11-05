"""Would the 2026 forecasts have been better trained without 2026?

When the June quarter's weeks became Final they entered the ADL+ECM's
training sample, and diesel's lag-weight sum fell from 0.814 (trained to the
end of 2025) to 0.444 (petrol 0.817 -> 0.760). About 60% of diesel's fall is
MBIE's fuel market adjustment: removing it from `importer_cost` takes the sum
back to 0.671. That is a statement about weights. This is the forecast test.

PRE-REGISTERED, written 5 Nov 2026 before any forecast number here was
computed (only the weight sums above had been seen):

  Primary  cut2025: identical to production except that training stops at
           the last week of 2025. Forecast inputs are the published data, as
           in production.
  Against  production (Final weeks up to each cutoff, 2026 included).
  Sample   forecast origins from 2 Jan 2026 with a known outcome, Diesel and
           Regular Petrol pooled.
  PASS     pooled MAE of cut2025 lower than production at h=1 AND h=2.
  FAIL     anything else.

  Diagnostics, not deciding: noadj (training on importer_cost minus MBIE's
  adjustment, `adjustment_cpl` from the archive's margin.csv, with margin and
  the ECM gap following; forecast inputs still published); per fuel; h=3;
  origins Jan-Jun vs Jul-Oct.

CAVEATS. n is about 43 origins per fuel, almost all inside one volatility
episode, so the result is a direction. The archive is the current vintage:
live, the 2026 weeks entered training only when MBIE finalised them (the June
quarter on 26 Aug), so production's 2026 forecasts here are a walk-forward
reconstruction, not the calls as published at the time.

ADDED AFTER THE FIRST RUN, 5 Nov 2026 — a diagnostic, not a blind test. The
first run failed, and the whole loss sat in Jan-Jun 2026, where the
current-vintage status lets production train on crisis weeks that were still
Provisional at the time. `--live-status` rebuilds the status a cutoff would
have seen: a week counts as Final only once its calendar quarter ended 61
days before the cutoff. 61 days is the one observed lag (June quarter, last
week 26 Jun, finalised 26 Aug 2026), applied to every quarter as an
assumption. Values stay the current vintage, MBIE's 23 Sep adjustment
included; only the training sample changes.

Usage:  python research/adl_train_cut.py [--archive-date 2026-11-05] [--live-status]
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

import adl_decay as ad   # noqa: E402  (archive loader and the fit)

bt = ad.bt
FUELS = ("Diesel", "Regular Petrol")
CUT = pd.Timestamp("2026-01-01")
VARIANTS = ("production", "cut2025", "noadj")
FINAL_LAG_DAYS = 61


def without_adjustment(d: pd.DataFrame, adj: pd.Series) -> pd.DataFrame:
    d2 = d.copy()
    d2["importer_cost"] = d.importer_cost - adj
    d2["d_cost"] = d2.importer_cost.diff()
    d2["importer_margin"] = d.importer_margin + adj
    d2["dev"] = (d2.importer_margin - d2.importer_margin.rolling(
        bt.ECM_WINDOW, min_periods=bt.ECM_WINDOW).mean()).shift(1)
    return d2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05")
    ap.add_argument("--live-status", action="store_true",
                    help="Final only once the week's quarter ended FINAL_LAG_DAYS before the cutoff")
    args = ap.parse_args()
    fc = ad.load_archive(args.archive_date)
    with zipfile.ZipFile(ad.CACHE / f"nz-fuel-{args.archive_date}.zip") as z:
        mg = pd.read_csv(io.BytesIO(z.read("margin.csv")), parse_dates=["week_date"])

    rows = []
    for fuel in FUELS:
        d = bt.load(fuel)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        cut = d.copy()
        cut["is_final"] = cut.is_final & (cut.index < CUT)
        adj = mg[mg.fuel == fuel].set_index("week_date").adjustment_cpl.reindex(d.index).fillna(0.0)
        noadj = without_adjustment(d, adj)
        train = {"production": d, "cut2025": cut, "noadj": noadj}
        q_end = d.index.to_period("Q").end_time.normalize()
        for t in range(int(np.searchsorted(d.index, CUT)), n):
            if args.live_status:
                known = np.asarray(q_end + pd.Timedelta(days=FINAL_LAG_DAYS) <= d.index[t])
                tr = {}
                for v, frame in train.items():
                    f = frame.copy()
                    f["is_final"] = f.is_final.to_numpy() & known
                    tr[v] = f
            else:
                tr = train
            r0 = {v: ad.fit(tr[v], t + 1) for v in VARIANTS}
            for h in bt.HORIZONS:
                if t + h >= n:
                    continue
                r = dict(fuel=fuel, date=d.index[t], h=h, price_now=retail[t],
                         actual=retail[t + h] - retail[t])
                for v, b in r0.items():
                    r[v] = bt.adl_forecast(d, t, b, h, True) * 1.15
                rows.append(r)
    res = pd.DataFrame(rows)

    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    chk = res.merge(pub[["date", "fuel", "h", "pred_adl_ecm"]], on=["date", "fuel", "h"])
    gap = (chk["price_now"] + chk["production"] - chk["pred_adl_ecm"]).abs().max()
    print(f"PLUMBING: {len(chk)} rows, max |production - published pred_adl_ecm| = {gap:.6f} c/L")
    if args.live_status:
        print("  (--live-status: production is no longer the published fit, so a gap is expected)")
    elif not gap < 0.01:
        return 1

    def block(sub: pd.DataFrame, title: str) -> None:
        print(f"\n{title}\nMAE c/L; % against production (negative = better)")
        print(f"  {'fuel':<15}{'h':>2}{'n':>4}{'production':>12}{'cut2025':>10}{'%':>7}{'noadj':>9}{'%':>7}")
        for h in bt.HORIZONS:
            for fuel in (*FUELS, "POOLED"):
                s = sub[sub.h == h] if fuel == "POOLED" else sub[(sub.h == h) & (sub.fuel == fuel)]
                m = {v: np.abs(s[v] - s.actual).mean() for v in VARIANTS}
                print(f"  {fuel:<15}{h:>2}{len(s):>4}{m['production']:>12.3f}"
                      f"{m['cut2025']:>10.3f}{(m['cut2025'] / m['production'] - 1) * 100:>6.1f}%"
                      f"{m['noadj']:>9.3f}{(m['noadj'] / m['production'] - 1) * 100:>6.1f}%")

    block(res, "ALL 2026 ORIGINS (the decision sample)")
    print("\nDECISION (pre-registered): pooled cut2025 < production at h=1 AND h=2")
    ok = []
    for h in (1, 2):
        s = res[res.h == h]
        p, c = (np.abs(s[v] - s.actual).mean() for v in ("production", "cut2025"))
        ok.append(c < p)
        print(f"  h={h}: production {p:.3f}  cut2025 {c:.3f}  -> {'yes' if c < p else 'NO'}")
    print(f"  => {'PASS' if all(ok) else 'FAIL'}")
    block(res[res.date < "2026-07-01"], "DIAGNOSTIC - origins Jan-Jun 2026")
    block(res[res.date >= "2026-07-01"], "DIAGNOSTIC - origins from 1 Jul 2026 "
          "(the load-review comparison after a finalisation)")

    print("\nLag weights at the newest cutoff: sum b0..b6, b0, g (ECM)")
    for fuel in FUELS:
        d = bt.load(fuel)
        cut = d.copy()
        cut["is_final"] = cut.is_final & (cut.index < CUT)
        last_final = d.index[d.is_final].max().date()
        for v, frame in (("production", d), ("cut2025", cut)):
            b = ad.fit(frame, len(frame))
            print(f"  {fuel:<15}{v:<11} sum {b[1:bt.K + 2].sum():.3f}  b0 {b[1]:+.3f}"
                  f"  g {b[-1]:+.3f}   (last Final week {last_final})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
