"""Should the ADL+ECM weight recent weeks more? A walk-forward test.

Today `pipeline/backtest.py` refits at every cutoff on all Final weeks since
2010, each with equal weight. Diesel's pass-through moved at the 2022 boundary
(`docs/research.md`, "Rolling window over all 22 years": modal lag 1 -> 2 after
Jan 2022, petrol unchanged), so an equal-weight fit averages today's market
with the refining era. The fix tested here keeps every week and the
specification and changes only the weights: a week `a` weeks older than the
cutoff counts 0.5 ** (a / 156) — a three-year half-life, the same three years
the model already waits for before its first call (MIN_TRAIN = 156).

PRE-REGISTERED, written 5 Nov 2026 before any number here was computed:

  Primary  decay, half-life 156 weeks, weighted least squares on the same
           Final rows, the same K = 6 and ECM term, the same h-step forecast.
  Against  the production fit (expanding, equal weights).
  Sample   every forecast origin the production backtest scores (2013 on),
           outcome known, Diesel and Regular Petrol pooled.
  PASS     pooled MAE lower than production at h=1 AND h=2 in non-crisis
           weeks, and not higher at h=1 or h=2 in crisis weeks.
  FAIL     anything else.

  Diagnostics, reported and not deciding: a rolling 260-week window (equal
  weights inside it); per-fuel cells; h=3; origins from 1 Apr 2022, where the
  hypothesis says the gain should be; the lag weights at the last cutoff.

Crisis = `crude_vol_regime == "high"`, a centred hindsight label used only to
split results, as in `backtest.py`.

PLUMBING. Panel and flags from the published archive, as in
`research/nowcast_backwardation.py`; the expanding fit here must reproduce the
archive's `pred_adl_ecm` before anything is read.

Usage:  python research/adl_decay.py [--archive-date 2026-11-05]
Fetches the archive once into data/adl_decay/. No warehouse, no capacity.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import backtest as bt   # noqa: E402

CACHE = ROOT / "data" / "adl_decay"
ARCHIVE = "https://nzfueldata.blob.core.windows.net/data/{d}/nz-fuel-{d}.zip"
FUELS = ("Diesel", "Regular Petrol")
HALF_LIFE = 156
ROLL = 260
VARIANTS = {"expanding": {}, "decay156": {"half_life": HALF_LIFE}, "roll260": {"window": ROLL}}
SPLIT_2022 = pd.Timestamp("2022-04-01")


def load_archive(date: str) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"nz-fuel-{date}.zip"
    if not path.exists():
        with urllib.request.urlopen(ARCHIVE.format(d=date), timeout=120) as r:
            path.write_bytes(r.read())
    with zipfile.ZipFile(path) as z:
        wp = pd.read_csv(io.BytesIO(z.read("weekly_prices.csv")))
        fc = pd.read_csv(io.BytesIO(z.read("forecasts.csv")), parse_dates=["week_date"])
    wp.rename(columns={"week_date": "Date", "fuel": "Fuel"}).to_csv(
        CACHE / "panel_weekly.csv", index=False)
    (fc[fc.horizon_weeks == 1][["week_date", "fuel", "crude_vol_regime",
                                "crude_episode_id", "crude_move_regime"]]
     .drop_duplicates(["week_date", "fuel"]).to_csv(CACHE / "period_flags.csv", index=False))
    bt.PANEL, bt.FLAGS = CACHE / "panel_weekly.csv", CACHE / "period_flags.csv"
    return fc


def fit(d: pd.DataFrame, upto: int, half_life: float | None = None,
        window: int | None = None) -> np.ndarray | None:
    """`bt.fit_adl(..., with_ecm=True)` with optional age weights or a window."""
    cols = [d.d_cost.shift(i).to_numpy() for i in range(bt.K + 1)] + [d.dev.to_numpy()]
    X = np.column_stack([np.ones(len(d))] + cols)[:upto]
    y = d.d_net.to_numpy()[:upto]
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & d.is_final.to_numpy()[:upto]
    age = (upto - 1) - np.arange(upto)
    if window is not None:
        ok &= age < window
    if ok.sum() < bt.MIN_TRAIN:
        return None
    w = 0.5 ** (age[ok] / half_life) if half_life else np.ones(ok.sum())
    sw = np.sqrt(w)
    return np.linalg.lstsq(X[ok] * sw[:, None], y[ok] * sw, rcond=None)[0]


def mae(s: pd.DataFrame, m: str) -> float:
    return float(np.abs(s[m] - s.actual).mean())


def table(sub: pd.DataFrame, title: str) -> None:
    print(f"\n{title}\nMAE c/L on the pump price; % = change against expanding (negative = better)")
    print(f"  {'fuel':<15}{'regime':<11}{'h':>2}{'n':>5}{'expanding':>11}"
          f"{'decay156':>10}{'%':>7}{'roll260':>10}{'%':>7}")
    for crisis, label in ((False, "non-crisis"), (True, "crisis")):
        for h in bt.HORIZONS:
            for fuel in (*FUELS, "POOLED"):
                s = sub[(sub.hi == crisis) & (sub.h == h)]
                if fuel != "POOLED":
                    s = s[s.fuel == fuel]
                if s.empty:
                    continue
                e, dcy, rl = mae(s, "expanding"), mae(s, "decay156"), mae(s, "roll260")
                print(f"  {fuel:<15}{label:<11}{h:>2}{len(s):>5}{e:>11.3f}"
                      f"{dcy:>10.3f}{(dcy / e - 1) * 100:>6.1f}%{rl:>10.3f}{(rl / e - 1) * 100:>6.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05")
    args = ap.parse_args()
    fc = load_archive(args.archive_date)

    rows, last_beta = [], {}
    for fuel in FUELS:
        d = bt.load(fuel)
        n = len(d)
        retail = d.adjusted_retail_price.to_numpy()
        hi = (d.crude_vol_regime == "high").to_numpy()
        for t in range(bt.MIN_TRAIN, n):
            betas = {v: fit(d, t + 1, **kw) for v, kw in VARIANTS.items()}
            if betas["expanding"] is None:
                continue
            for h in bt.HORIZONS:
                r = dict(fuel=fuel, date=d.index[t], h=h, hi=bool(hi[t]),
                         price_now=retail[t],
                         actual=retail[t + h] - retail[t] if t + h < n else np.nan)
                for v, b in betas.items():
                    f = bt.adl_forecast(d, t, b, h, True) if b is not None else np.nan
                    r[v] = f * 1.15 if np.isfinite(f) else np.nan
                rows.append(r)
            last_beta[fuel] = betas
    res = pd.DataFrame(rows)

    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    chk = res.merge(pub[["date", "fuel", "h", "pred_adl_ecm"]], on=["date", "fuel", "h"])
    gap = (chk["price_now"] + chk["expanding"] - chk["pred_adl_ecm"]).abs().max()
    print(f"PLUMBING: {len(chk)} rows, max |expanding - published pred_adl_ecm| = {gap:.6f} c/L")
    if not gap < 0.01:
        print("  does not reproduce production; nothing below can be read", file=sys.stderr)
        return 1

    ev = res[np.isfinite(res.actual)].dropna(subset=list(VARIANTS))
    print(f"scored rows: {len(ev)}, origins {ev.date.min().date()} .. {ev.date.max().date()}")
    table(ev, "ALL ORIGINS (the decision sample)")

    print("\nDECISION (pre-registered): pooled decay156 < expanding at h=1 and h=2 in "
          "non-crisis weeks, and <= in crisis weeks")
    ok = []
    for crisis, strict in ((False, True), (True, False)):
        for h in (1, 2):
            s = ev[(ev.hi == crisis) & (ev.h == h)]
            e, dcy = mae(s, "expanding"), mae(s, "decay156")
            good = dcy < e if strict else dcy <= e
            ok.append(good)
            print(f"  {'crisis' if crisis else 'non-crisis':<11} h={h}: expanding {e:.3f}  "
                  f"decay156 {dcy:.3f}  -> {'yes' if good else 'NO'}")
    print(f"  => {'PASS' if all(ok) else 'FAIL'}")

    table(ev[ev.date >= SPLIT_2022], "DIAGNOSTIC - origins from 1 Apr 2022")

    print("\nLag weights at the last cutoff: const, b0..b6, sum b, g (ECM)")
    for fuel, betas in last_beta.items():
        for v, b in betas.items():
            if b is None:
                continue
            bs = b[1:bt.K + 2]
            print(f"  {fuel:<15}{v:<10} " + " ".join(f"{x:+.3f}" for x in b[:bt.K + 2])
                  + f"  sum {bs.sum():.3f}  g {b[-1]:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
