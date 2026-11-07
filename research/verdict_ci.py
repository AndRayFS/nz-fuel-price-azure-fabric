"""Do the verdicts of tries 1, 2 and 4 survive a confidence interval? 7 Nov 2026.

Pre-registered in research/model_plateau_review.md, section 5, with its
amendment, before this ran. Nothing is re-implemented: each try's own script
produces its per-week forecasts, and this file only resamples them.

  try 1  nowcast_in_adl.py     adl_ecm_nc vs adl_ecm, non-crisis weeks
  try 2  nowcast_backwardation nc_fut vs adl_ecm, nowcast weeks from 4 Sep 2026
  try 4  adl_decay.py          decay156 vs expanding, every origin since 2013
  part 2 nowcast_in_adl.py     adl_ecm_nc vs adl_ecm, every crisis week

Statistic: MAE ratio variant / production. Moving-block bootstrap over forecast
origins (both fuels of a date resampled together when pooled), 2,000
resamples, 90% percentile CI. Block 8 weeks when n >= 32, else 2.

Rules:
  a verdict of "better" stands if the CI's upper end < 1
  a verdict of "worse"  stands if the CI's lower end > 1
  otherwise it is "not detectable"
  part 2: "does not hurt in crisis weeks" if the CI's upper end < 1.05

Reads the published archive (default 2026-11-05) and, for try 2, Yahoo, FRED
and ComCom, as nowcast_backwardation.py always has. No warehouse.

    python research/verdict_ci.py
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "research"))

import backtest as bt                    # noqa: E402
import adl_decay                         # noqa: E402
import nowcast_backwardation as nb       # noqa: E402
import nowcast_in_adl as nai             # noqa: E402

OUT = ROOT / "data" / "verdict_ci"
REPS, SEED, LEVEL, HURT = 2000, 20261107, 0.90, 1.05
FUELS = ("Diesel", "Regular Petrol")
Y2026 = pd.Timestamp("2026-01-01")
BACKW_ORIGIN = pd.Timestamp("2026-08-28")   # nowcast week 4 Sep = origin 28 Aug


def block_len(n: int) -> int:
    return 8 if n >= 32 else 2


def ratio_ci(s: pd.DataFrame, var: str, base: str) -> tuple[int, float, float, float]:
    s = s.dropna(subset=[var, base, "actual"])
    g = (pd.DataFrame({"date": s.date,
                       "v": (s[var] - s.actual).abs(),
                       "b": (s[base] - s.actual).abs()})
         .groupby("date")[["v", "b"]].sum().sort_index())
    v, b = g.v.to_numpy(), g.b.to_numpy()
    n = len(g)
    if n < 4:
        return n, np.nan, np.nan, np.nan
    L = block_len(n)
    k = int(np.ceil(n / L))
    rng = np.random.default_rng(SEED)
    starts = rng.integers(0, n - L + 1, size=(REPS, k))
    idx = (starts[:, :, None] + np.arange(L)).reshape(REPS, -1)[:, :n]
    r = v[idx].sum(1) / b[idx].sum(1)
    lo, hi = np.quantile(r, [(1 - LEVEL) / 2, 1 - (1 - LEVEL) / 2])
    return n, v.sum() / b.sum(), lo, hi


def verdict(rule: str, lo: float, hi: float) -> str:
    if not np.isfinite(lo):
        return "too few weeks"
    if rule == "better":
        return "stands" if hi < 1 else "not detectable"
    if rule == "worse":
        return "stands" if lo > 1 else "not detectable"
    return "does not hurt" if hi < HURT else "not shown"


def captured(module, argv: list[str]) -> dict[str, pd.DataFrame]:
    """Run a try's own main() and keep the frames it passes to table()."""
    got: dict[str, pd.DataFrame] = {}
    orig, old_argv = module.table, sys.argv
    module.table = lambda sub, title: got.__setitem__(title, sub.copy())
    sys.argv = [module.__file__, *argv]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = module.main()
    finally:
        module.table, sys.argv = orig, old_argv
    plumbing = [x for x in buf.getvalue().splitlines() if x.startswith("PLUMBING")]
    print(f"{module.__name__}: {plumbing[0] if plumbing else 'no plumbing line'}")
    if rc != 0 or not got:
        raise SystemExit(f"{module.__name__} did not reproduce production:\n"
                         + buf.getvalue()[-1500:])
    return got


def fred_or_stub() -> None:
    """Try 2's script also builds a spot-Brent nowcast from FRED. Its decision,
    and this file, use only nc_fut, so when FRED cannot be reached the spot
    column is fed the futures series (written here, never into try 2's cache)
    and is not reported."""
    orig = nb.fetch

    def fetch(url: str, name: str) -> Path:
        if url != nb.FRED:
            return orig(url, name)
        try:
            return orig(url, name)
        except OSError as e:
            print(f"FRED unreachable ({type(e).__name__}): spot column stubbed, not reported",
                  file=sys.stderr)
            OUT.mkdir(parents=True, exist_ok=True)
            p = OUT / "fred_stub.csv"
            fut = nb.yahoo("BZ=F")
            pd.DataFrame({"DATE": pd.DatetimeIndex(fut.index).strftime("%Y-%m-%d"),
                          "DCOILBRENTEU": fut.to_numpy()}).to_csv(p, index=False)
            return p

    nb.fetch = fetch


def nowcast_rows(archive: str) -> pd.DataFrame:
    """Try 1's per-week results, written to data/verdict_ci/, not data/."""
    fc = adl_decay.load_archive(archive)            # points bt at the archive
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    old_root, old_argv = nai.ROOT, sys.argv
    nai.ROOT, sys.argv = OUT, [nai.__file__, "--save"]
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = nai.main()
    finally:
        nai.ROOT, sys.argv = old_root, old_argv
    if rc != 0:
        raise SystemExit("nowcast_in_adl failed")
    res = pd.read_csv(OUT / "data" / "nowcast_results.csv", parse_dates=["date"])
    pub = fc.rename(columns={"week_date": "date", "horizon_weeks": "h"})
    chk = res.merge(pub[["date", "fuel", "h", "pred_adl_ecm"]], on=["date", "fuel", "h"])
    gap = (chk.price_now + chk.adl_ecm - chk.pred_adl_ecm).abs().max()
    print(f"nowcast_in_adl: PLUMBING: {len(chk)} rows, max |reproduced - published"
          f" pred_adl_ecm| = {gap:.6f} c/L")
    if not gap < 0.01:
        raise SystemExit("nowcast_in_adl does not reproduce production")
    res["hi"] = res.hi.astype(str).str.lower().eq("true")
    return res[res.outcome_known.astype(str).str.lower().eq("true")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive-date", default="2026-11-05")
    args = ap.parse_args()
    a = ["--archive-date", args.archive_date]

    nc = nowcast_rows(args.archive_date)
    t4 = captured(adl_decay, a)["ALL ORIGINS (the decision sample)"]
    fred_or_stub()
    t2 = captured(nb, a)["PRIMARY - nowcast week from 2026-09-04 (backwardation)"]

    rows = []

    def add(test, sample, rule, frame, var, base, horizons, fuels, pooled=True):
        groups = [(f, frame[frame.fuel == f]) for f in fuels]
        if pooled:
            groups.append(("pooled D+R", frame[frame.fuel.isin(FUELS)]))
        for fuel, sub in groups:
            for h in horizons:
                n, p, lo, hi = ratio_ci(sub[sub.h == h], var, base)
                rows.append(dict(test=test, sample=sample, fuel=fuel, h=h, n=n,
                                 block=block_len(n), change=(p - 1) * 100,
                                 ci_lo=(lo - 1) * 100, ci_hi=(hi - 1) * 100,
                                 verdict=verdict(rule, lo, hi)))

    all3 = (*FUELS, "Premium Petrol 95R")
    add("try 1", "non-crisis", "better", nc[~nc.hi], "adl_ecm_nc", "adl_ecm", (1, 2, 3), all3)
    add("try 2", "backwardation", "worse", t2, "nc_fut", "adl_ecm", (1, 2), FUELS)
    for crisis, label in ((False, "non-crisis"), (True, "crisis")):
        add("try 4", label, "worse", t4[t4.hi == crisis], "decay156", "expanding", (1, 2), FUELS)
    cr = nc[nc.hi]
    add("part 2", "all crisis weeks", "hurt", cr, "adl_ecm_nc", "adl_ecm", (1, 2, 3), all3)
    for label, sub in (("crisis, before 2026", cr[cr.date < Y2026]),
                       ("crisis, 2026", cr[cr.date >= Y2026]),
                       ("crisis, backwardation", cr[cr.date >= BACKW_ORIGIN])):
        add("part 2 (descriptive)", label, "hurt", sub, "adl_ecm_nc", "adl_ecm", (1, 2), FUELS)

    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "verdict_ci.csv", index=False)
    pd.set_option("display.width", 200)
    print("\nMAE change, variant vs production, % (negative = variant better); "
          f"{int(LEVEL * 100)}% block-bootstrap CI\n")
    print(out.round(1).to_string(index=False))
    print(f"\n-> {OUT / 'verdict_ci.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
