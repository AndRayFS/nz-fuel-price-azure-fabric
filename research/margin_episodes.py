"""What happened after the importer margin was crushed — the historical record.

The question this answers is not "is the margin low" but "the margin has been
this low before; what came next, and how reliably". It exists because the
compression itself is the most-quoted fact about a fuel price shock and the
least-checkable one: the industry says margins are thin, and a reader has no
denominator to test that against.

NORMALISATION IS NOT OPTIONAL. The margin's level is not comparable across
the series — the annual mean runs 18 c/L in 2004 to 47 in 2026, roughly a
tripling, for reasons that have nothing to do with any shock. So every
statement here is about the *gap* between the margin and its own trailing
104-week mean, lagged one week so the norm never contains the week being
judged. A raw threshold on the margin would select 2004-2009 almost
exclusively and measure the trend rather than the event.

THE CONDITIONING SET IS WEEKS, NOT EPISODES, and that is a real limitation
rather than a choice. Compressions arrive in runs — five consecutive weeks in
Aug 2023, seven in Mar-Apr 2026 — so 28 diesel weeks are perhaps seven
independent events. Quantiles below are over weeks; read them as describing
the shape of the conditional distribution, never as 28 draws. The episode
count is printed next to every n for exactly this reason.

WHAT IS DELIBERATELY NOT CLAIMED. That a compression *causes* the pump price
to rise. Both are downstream of the same cost shock, and the decomposition in
docs/research.md ("What actually drove pump prices through the 2026 crisis")
shows margin recovery contributing 6% of the 2026 diesel rise against cost's
78%. The compression is a marker of a cost shock already in the system and not
yet in the price. That is enough for what it is used for, and it is less than
it looks like.

Usage:  python research/margin_episodes.py [--threshold -10]
Offline. Reads data/panel_weekly.csv. No warehouse, no capacity.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
PANEL = ROOT / "data" / "panel_weekly.csv"
FUELS = ("Regular Petrol", "Diesel")

NORM_WINDOW = 104       # trailing weeks defining "normal", as in the ECM work
NORM_MIN = 52           # start reporting once half a window exists
HORIZONS = (4, 8, 13, 26)
RECOVERED = -5.0        # "back to normal" = gap no worse than this
EPISODE_GAP_DAYS = 182  # runs this far apart count as separate episodes


def load() -> pd.DataFrame:
    p = pd.read_csv(PANEL, parse_dates=["Date"])
    return p.sort_values(["Fuel", "Date"])


def with_gap(d: pd.DataFrame) -> pd.DataFrame:
    """Margin minus its own trailing mean. `shift(1)` keeps the week out of
    its own benchmark — without it a deep week drags the norm toward itself
    and the gap is understated exactly where it matters most."""
    d = d.copy().reset_index(drop=True)
    d["norm"] = (
        d.importer_margin.rolling(NORM_WINDOW, min_periods=NORM_MIN).mean().shift(1)
    )
    d["gap"] = d.importer_margin - d["norm"]
    return d


def episode_count(dates: pd.Series) -> int:
    """Runs separated by less than EPISODE_GAP_DAYS are one episode."""
    n, last = 0, None
    for t in sorted(dates):
        if last is None or (t - last).days >= EPISODE_GAP_DAYS:
            n += 1
        last = t
    return n


def weeks_to_recover(d: pd.DataFrame, i: int, limit: int = 78) -> float:
    for k in range(1, limit + 1):
        if i + k >= len(d):
            return np.nan
        if d.loc[i + k, "gap"] >= RECOVERED:
            return k
    return np.nan


def report(fuel: str, d: pd.DataFrame, threshold: float) -> None:
    d = with_gap(d)
    base = d.dropna(subset=["gap"])
    cur = d.iloc[-1]

    print(f"\n{'=' * 78}")
    print(f"{fuel} — n={len(base)} weeks carry a trailing norm "
          f"({base.Date.min().date()} to {base.Date.max().date()})")
    print(f"TODAY {cur.Date.date()}: margin {cur.importer_margin:.1f}, "
          f"norm {cur['norm']:.1f}, gap {cur.gap:+.1f} c/L")

    sel = base[base.gap <= threshold]
    # Only weeks whose outcome is observable can answer the question.
    done = sel[sel.index + max(HORIZONS) < len(d)]
    print(f"\nweeks with gap <= {threshold:+.0f}: {len(sel)} "
          f"({100 * len(sel) / len(base):.1f}% of the series), "
          f"{episode_count(sel.Date)} distinct episodes")
    print(f"of those, {len(done)} are old enough to score at +{max(HORIZONS)} weeks "
          f"({episode_count(done.Date)} episodes)")

    if not len(done):
        print("  nothing scoreable at this threshold")
        return

    print(f"\n  {'horizon':<9}{'gap closes by (c/L)':^30}{'still':>8}   "
          f"{'pump price change (c/L)':^28}")
    print(f"  {'':<9}{'p25':>10}{'median':>10}{'p75':>10}{'<= thr':>8}   "
          f"{'p25':>9}{'median':>9}{'p75':>9}")
    for k in HORIZONS:
        later_gap = d.gap.reindex(done.index + k).to_numpy()
        closes = later_gap - done.gap.to_numpy()
        dr = (d.adjusted_retail_price.reindex(done.index + k).to_numpy()
              - done.adjusted_retail_price.to_numpy())
        still = 100 * np.mean(later_gap <= threshold)
        print(f"  +{k:<8}wk"
              f"{np.nanpercentile(closes, 25):+10.1f}"
              f"{np.nanmedian(closes):+10.1f}"
              f"{np.nanpercentile(closes, 75):+10.1f}"
              f"{still:7.0f}%   "
              f"{np.nanpercentile(dr, 25):+9.1f}"
              f"{np.nanmedian(dr):+9.1f}"
              f"{np.nanpercentile(dr, 75):+9.1f}")

    # The comparison that makes the pump numbers mean anything: the same
    # horizons measured from every week, not only the compressed ones.
    print("\n  unconditional pump change, same horizons, all weeks:")
    line = "   "
    for k in HORIZONS:
        dr = (base.adjusted_retail_price.shift(-k) - base.adjusted_retail_price)
        line += f" +{k}wk {dr.median():+5.1f}  "
    print(line)

    rec = [weeks_to_recover(d, i) for i in done.index]
    got = [r for r in rec if not np.isnan(r)]
    print(f"\n  returned to within {abs(RECOVERED):.0f} c/L of normal: "
          f"{len(got)}/{len(rec)} weeks"
          + (f", median {np.median(got):.0f} wk, range {min(got):.0f}-{max(got):.0f}"
             if got else ""))

    # The individual weeks, because with n this small the table above is a
    # summary of something a reader should be able to see in full.
    print(f"\n  every qualifying week:")
    print(f"  {'week':<12}{'margin':>8}{'norm':>7}{'gap':>7}"
          + "".join(f"{'gap+' + str(k):>9}" for k in (4, 13))
          + "".join(f"{'pump+' + str(k):>10}" for k in (4, 13)))
    for i, r in sel.iterrows():
        cells = ""
        for k in (4, 13):
            v = d.gap.get(i + k, np.nan)
            cells += f"{v:+9.1f}" if pd.notna(v) else f"{'-':>9}"
        for k in (4, 13):
            v = d.adjusted_retail_price.get(i + k, np.nan)
            dv = v - r.adjusted_retail_price if pd.notna(v) else np.nan
            cells += f"{dv:+10.1f}" if pd.notna(dv) else f"{'-':>10}"
        print(f"  {str(r.Date.date()):<12}{r.importer_margin:8.1f}"
              f"{r['norm']:7.1f}{r.gap:+7.1f}{cells}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=-10.0,
                    help="gap in c/L below the trailing norm (default -10)")
    args = ap.parse_args()

    p = load()
    for fuel in FUELS:
        report(fuel, p[p.Fuel == fuel], args.threshold)


if __name__ == "__main__":
    main()
