"""M5 of the 19 Nov 2026 review: how much does MBIE's 23 Sep cost revision
move the backtest's 2026 calls?

The claim on Track record — "scored on today's revised data, which flatters
both methods alike" — was never measured. The largest known revision is the
fuel market adjustment (docs/mbie_notes.md, 23 Sep 2026): from 27 Feb 2026
`Importer cost` up and `Importer margin` down by the same amount, retail
untouched. "No change" cannot see it; the model sees it twice, in `d_cost`
and in the margin's distance from its norm (`dev`).

WHAT THIS DOES. Takes the adjustment out again — cost minus `adjustment_cpl`,
margin plus it, 27 Feb – 11 Sep 2026, from `margin.csv` of the 9 Nov 2026
archive, the vintage `data/panel_weekly.csv` is — and reruns the production
walk-forward. Only calls made from weeks 27 Feb – 11 Sep are compared: before
27 Feb nothing differs, and from 18 Sep the live chain itself saw adjusted
data (those weeks arrived adjusted on 24 Sep), so the backtest is already
what it saw.

WHAT THIS IS NOT. A real-time backtest. Every other revision stays in, and
for 18 Mar – 1 Jul the live chain had no cost at all (MBIE suspended it and
filled it in later), so no vintage of those calls ever existed. This isolates
one revision, the largest, and measures what it is worth.

Usage:  python research/review_m5_unadjusted_cost.py
Offline. Reads data/panel_weekly.csv, data/period_flags.csv, the 9 Nov
archive and the cached Brent/FX files. No warehouse, no capacity.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

import wf_harness as wf

ARCHIVE = wf.ROOT / "data" / "publish" / "nz-fuel-2026-11-09.zip"
FROM, TO = pd.Timestamp("2026-02-27"), pd.Timestamp("2026-09-11")


def adjustment() -> pd.DataFrame:
    with zipfile.ZipFile(ARCHIVE) as z, z.open("margin.csv") as f:
        m = pd.read_csv(f, parse_dates=["week_date"])
    a = m.loc[m.adjustment_cpl.notna(), ["week_date", "fuel", "adjustment_cpl", "importer_margin"]]
    assert a.week_date.min() == FROM and a.week_date.max() == TO, (a.week_date.min(), a.week_date.max())
    return a


def unadjusted_frames(adj: pd.DataFrame) -> dict:
    p = pd.read_csv(wf.bt.PANEL, parse_dates=["Date"])
    m = p.merge(adj, left_on=["Date", "Fuel"], right_on=["week_date", "fuel"], how="left")
    # same vintage: the archive's margin and the panel's must be one number
    gap = (m.importer_margin_x - m.importer_margin_y).abs().max()
    assert gap < 1e-9, f"panel and archive disagree on the margin by {gap}"
    a = m.adjustment_cpl.fillna(0.0)
    p["importer_cost"] = p.importer_cost - a.to_numpy()
    p["importer_margin"] = p.importer_margin + a.to_numpy()
    tmp = Path(tempfile.mkdtemp()) / "panel_unadjusted.csv"
    p.to_csv(tmp, index=False)
    saved = wf.bt.PANEL
    try:
        wf.bt.PANEL = tmp          # bt.load recomputes d_cost and dev from it
        return wf.production_frames()
    finally:
        wf.bt.PANEL = saved


def main() -> None:
    adj = adjustment()
    print("adjustment, c/L, 27 Feb - 11 Sep 2026:")
    print(adj.groupby("fuel").adjustment_cpl.describe()[["count", "mean", "min", "max"]].round(2).to_string())

    base = wf.walk_forward(wf.production_frames(), t_from=FROM, t_to=TO)
    alt = wf.walk_forward(unadjusted_frames(adj), t_from=FROM, t_to=TO)
    m = base.merge(alt, on=["fuel", "date", "h"], suffixes=("", "_u"))
    assert (m.actual.fillna(-1e9) == m.actual_u.fillna(-1e9)).all()
    m = m[m.outcome_known]

    print("\nCalls from weeks 27 Feb - 11 Sep 2026. MAE in c/L on the pump price;")
    print("'today' = the backtest as published, 'as seen' = with the adjustment taken out.")
    print(f"{'fuel':20s} {'h':>2} {'n':>3} {'naive':>7} | {'adl_ecm':>8} {'as seen':>8} | "
          f"{'nowcast':>8} {'as seen':>8} | {'mean |call diff|':>16} {'max':>6}")
    for (fuel, h), g in m.groupby(["fuel", "h"]):
        mae = lambda c: (g.actual - g[c]).abs().mean()
        d = (g.nowcast - g.nowcast_u).abs()
        print(f"{fuel:20s} {h:>2} {len(g):>3} {g.actual.abs().mean():7.2f} | "
              f"{mae('adl_ecm'):8.2f} {mae('adl_ecm_u'):8.2f} | {mae('nowcast'):8.2f} {mae('nowcast_u'):8.2f} | "
              f"{d.mean():16.2f} {d.max():6.2f}")

    print("\nSkill against naive, nowcast (1 - MAE/MAE_naive), pooled over the three fuels:")
    for h, g in m.groupby("h"):
        nv = g.actual.abs().mean()
        s0 = 1 - (g.actual - g.nowcast).abs().mean() / nv
        s1 = 1 - (g.actual - g.nowcast_u).abs().mean() / nv
        print(f"  h={h}: today {s0:+.3f}   as seen {s1:+.3f}   flattery {s0 - s1:+.3f}")


if __name__ == "__main__":
    main()
