"""W26: production trained without the window MBIE rebuilt — does it forecast
better after it?

PRE-REGISTERED, written 27 Nov 2026 before any number in this file was
computed. Seen before writing: `research/adl_train_cut.py --live-status` on
the 26 Nov archive (training to the end of 2025 against the ONE-margin-lag
ECM, origins from 1 Jul 2026: diesel -14.6% / -6.3% / -7.1% MAE at h=1/2/3,
petrol -8.2% / +9.8% / +6.5%), and the margin and cost series of 2026
(docs/research.md, "Diesel 2026: where it stands"). Not seen: any forecast
from W25's production or from a model with a hole.

THE HOLE (docs/workstreams.md, W26, step 0, owner's decision 27 Nov 2026):
option A, MBIE's suspension and rebuild of importer cost, 18 Mar - 1 Jul 2026.
  strict (primary)  equations dated 20 Mar - 21 Aug 2026: every equation whose
                    cost lags (b0..b6: week t's oldest is cost t-6 minus t-7)
                    or margin terms reach a rebuilt week.
  plain             equations dated 20 Mar - 3 Jul 2026.
The hole is a training mask: those weeks' rows leave the fit, and the same
mask applies to the nowcast's own regression, which production trains on the
same Final flag. The 104-week norm behind the margin term keeps the window
(accepted in W26). Forecasts are still made FOR the hole's weeks; only the
training changes.

PRODUCTION here is pipeline/backtest.py as it runs since W25: `fit_adl` with
two margin lags for Diesel and one for Regular Petrol (`bt.ECM_LAGS`), the
call Report 1 shows being the nowcast path (`nowcast.forecast_with_nowcast`),
with `adl_ecm` where no nowcast exists.

STATUS. `--live-status` as in adl_train_cut.py: a week counts as Final only
once its calendar quarter ended 61 days before the cutoff. Values are the
26 Nov archive's.

EXPECTED, AND CHECKED (P2): under the 61-day rule no week of July - September
2026 is Final at any origin up to 20 Nov 2026 (that quarter counts from
30 Nov). So the strict and plain holes train on the same rows here and must
give identical forecasts; they first differ after 30 Nov 2026.

DECISION SAMPLE. Origins from 5 Jun 2026, the first stamped week at which a
hole week (20 and 27 Mar, Q1) counts as Final, to the newest with a known
outcome. Before 5 Jun production and the hole train on the same rows. From
5 Jun to 28 Aug they differ by two weeks; from 4 Sep (Q2 Final) by sixteen.

RULE, per fuel, on the nowcast path:
  PASS  the strict hole's MAE is lower than production's at h=1 AND h=2.
  FAIL  anything else.
Diesel is the primary. Petrol takes its own verdict by the same rule. A PASS
on about 24 origins, about 11 of them with the full difference, is a
direction; whether to ship is the owner's decision (W26, risks).

PLUMBING, before anything else:
  P1  production with the archive's own status reproduces the archive's
      `pred_adl_ecm` on every 2026 origin to 0.01 c/L. `pred_nowcast` is
      reported, not gated: the cached Brent may differ from what Yahoo served
      on the day.
  P2  strict and plain give identical forecasts on the decision sample.

DIAGNOSTICS, deciding nothing: the plain hole; option C (all of 2026 out);
the adl_ecm path; h=3; origins 5 Jun - 28 Aug against from 4 Sep; the sum
b0..b6 at the newest cutoff under each variant.

Usage:  python research/w26_train_hole.py [--archive-date 2026-11-26]
Offline: the archive zip in data/adl_decay/, Brent and NZD/USD from the
cached daily files in data/ (research/wf_harness.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "pipeline"))

import adl_decay as ad    # noqa: E402  (archive loader; repoints bt.PANEL)
import wf_harness as wf   # noqa: E402  (cached Brent in NZ c/L)

bt = ad.bt
nc = wf.nc
FUELS = ("Diesel", "Regular Petrol")
FINAL_LAG_DAYS = 61
HOLES = {
    "strict": (pd.Timestamp("2026-03-20"), pd.Timestamp("2026-08-21")),
    "plain": (pd.Timestamp("2026-03-20"), pd.Timestamp("2026-07-03")),
}
CUT_C = pd.Timestamp("2026-01-01")
ORIGINS_FROM = pd.Timestamp("2026-06-05")
SPLIT = pd.Timestamp("2026-09-04")
VARIANTS = ("production", "strict", "plain", "C")


def masks(d: pd.DataFrame) -> dict:
    """Training rows each variant may use, before the live status."""
    idx = d.index
    out = {"production": np.ones(len(d), bool)}
    for name, (a, b) in HOLES.items():
        out[name] = ~((idx >= a) & (idx <= b))
    out["C"] = np.asarray(idx < CUT_C)
    return out


def run(fuel: str, d: pd.DataFrame, cpl: pd.Series, live: bool, t_from: pd.Timestamp,
        variants=VARIANTS) -> pd.DataFrame:
    lags = bt.ECM_LAGS.get(fuel, 1)
    n = len(d)
    retail = d.adjusted_retail_price.to_numpy()
    d_cost = d.d_cost.to_numpy()
    stamps = d.index.append(pd.DatetimeIndex([d.index[-1] + pd.Timedelta(days=7)]))
    x3 = nc.features(cpl, stamps)["x3"].to_numpy()
    base_final = d.is_final.to_numpy()
    q_end = d.index.to_period("Q").end_time.normalize()
    mk = masks(d)
    rows = []
    for t in range(int(np.searchsorted(d.index, t_from)), n):
        known = (np.asarray(q_end + pd.Timedelta(days=FINAL_LAG_DAYS) <= d.index[t])
                 if live else np.ones(n, bool))
        for v in variants:
            f = d.copy()
            f["is_final"] = base_final & known & mk[v]
            beta = bt.fit_adl(f, t + 1, with_ecm=True, ecm_lags=lags)
            if beta is None:
                continue
            ncv = nc.nowcast_at(x3, d_cost, f.is_final.to_numpy(), t)
            for h in bt.HORIZONS:
                actual = (retail[t + h] - retail[t]) if t + h < n else np.nan
                e = bt.adl_forecast(f, t, beta, h, True, lags)
                w = (nc.forecast_with_nowcast(f, t, beta, h, True, ncv, lags)
                     if np.isfinite(ncv) else e)
                rows.append(dict(fuel=fuel, date=d.index[t], h=h, variant=v,
                                 price_now=retail[t], actual=actual,
                                 adl_ecm=e * 1.15, nowcast=w * 1.15,
                                 bsum=float(beta[1:bt.K + 2].sum())))
    return pd.DataFrame(rows)


def mae(s: pd.DataFrame, col: str) -> float:
    return float(np.abs(s[col] - s.actual).mean())


def table(res: pd.DataFrame, col: str, title: str) -> None:
    print(f"\n{title} — {col} path, MAE c/L; % against production (negative = better)")
    print(f"  {'fuel':<15}{'h':>2}{'n':>4}{'production':>11}" +
          "".join(f"{v:>9}{'%':>7}" for v in VARIANTS[1:]))
    for fuel in FUELS:
        for h in bt.HORIZONS:
            s = res[(res.fuel == fuel) & (res.h == h)]
            p = mae(s[s.variant == "production"], col)
            n = int((s.variant == "production").sum())
            cells = ""
            for v in VARIANTS[1:]:
                m = mae(s[s.variant == v], col)
                cells += f"{m:>9.3f}{(m / p - 1) * 100:>6.1f}%"
            print(f"  {fuel:<15}{h:>2}{n:>4}{p:>11.3f}{cells}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-26")
    args = ap.parse_args()
    fc = ad.load_archive(args.archive_date)
    cpl = wf.cached_cpl()
    frames = {f: bt.load(f) for f in FUELS}

    # P1: production on the archive's own status reproduces the archive.
    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    p1 = pd.concat([run(f, d, cpl, live=False, t_from=pd.Timestamp("2026-01-01"),
                        variants=("production",)) for f, d in frames.items()])
    chk = p1.merge(pub[["date", "fuel", "h", "pred_adl_ecm", "pred_nowcast"]],
                   on=["date", "fuel", "h"])
    g_ecm = (chk.price_now + chk.adl_ecm - chk.pred_adl_ecm).abs().max()
    g_nc = (chk.price_now + chk.nowcast - chk.pred_nowcast).abs()
    print(f"P1: {len(chk)} rows; max |production - published pred_adl_ecm| = {g_ecm:.6f} c/L")
    print(f"    pred_nowcast, reported: max |diff| {g_nc.max():.4f} c/L, "
          f"rows over 0.01: {(g_nc > 0.01).sum()}")
    if not g_ecm < 0.01:
        print("P1 FAILED: stop")
        return 1

    res = pd.concat([run(f, d, cpl, live=True, t_from=ORIGINS_FROM) for f, d in frames.items()])
    res = res[np.isfinite(res.actual)]

    # P2: strict and plain identical on the decision sample.
    a = res[res.variant == "strict"].set_index(["fuel", "date", "h"])
    b = res[res.variant == "plain"].set_index(["fuel", "date", "h"])
    g2 = max((a.nowcast - b.nowcast).abs().max(), (a.adl_ecm - b.adl_ecm).abs().max())
    print(f"P2: max |strict - plain| on the decision sample = {g2:.2e} c/L "
          f"-> {'identical, as expected' if g2 < 1e-9 else 'NOT identical'}")

    print(f"\nDecision sample: origins {res.date.min():%d %b %Y} - {res.date.max():%d %b %Y}")
    table(res, "nowcast", "DECISION SAMPLE")
    print("\nRULE (pre-registered), per fuel: strict < production at h=1 AND h=2, nowcast path")
    for fuel in FUELS:
        ok = []
        for h in (1, 2):
            s = res[(res.fuel == fuel) & (res.h == h)]
            p, q = mae(s[s.variant == "production"], "nowcast"), mae(s[s.variant == "strict"], "nowcast")
            ok.append(q < p)
            print(f"  {fuel:<15} h={h}: production {p:.3f}  strict {q:.3f}  -> {'yes' if q < p else 'NO'}")
        print(f"  {fuel:<15} => {'PASS' if all(ok) else 'FAIL'}{'  (primary)' if fuel == 'Diesel' else ''}")

    print("\nDIAGNOSTICS, deciding nothing")
    table(res, "adl_ecm", "Decision sample")
    table(res[res.date < SPLIT], "nowcast", "Origins 5 Jun - 28 Aug (hole = two March weeks)")
    table(res[res.date >= SPLIT], "nowcast", "Origins from 4 Sep (hole = sixteen weeks)")
    last = res.date.max()
    print(f"\nSum b0..b6 at the newest origin, {last:%d %b %Y}, live status:")
    for fuel in FUELS:
        s = res[(res.fuel == fuel) & (res.date == last) & (res.h == 1)].set_index("variant").bsum
        print(f"  {fuel:<15}" + "  ".join(f"{v} {s[v]:.3f}" for v in VARIANTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
