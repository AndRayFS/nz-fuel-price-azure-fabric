"""Does a futures roll inside the nowcast's window cost it its edge? 7 Nov 2026.

Background, measured the same day on two years of Yahoo data (scratch check):
Yahoo's daily BZ=F is the calendar front contract and switches at expiry; its
intraday series switches 4-9 trading days earlier. The 18 Sep "wrong point"
(98.77, later 103.87) was the next contract, not an error. The nowcast's
feature, mean(Mon-Wed of week t+1) - mean(Mon-Fri of week t), is built from
the daily series, so when an expiry falls inside that window the feature
carries the gap between two contracts (2025: 0.3-1.25 USD; 2026: up to 7).

Roll week: an expiry E with Mon of week t <= E < Wed of week t+1, where the
origin `date` is week t's Friday stamp.

Expiry calendar (ICE Brent; NYMEX BZ follows it), London business days:
  contracts to Feb 2016: the business day before the 15th calendar day before
    the contract month's first day (if that day is not a business day, the
    business day before the one preceding it);
  contracts from Mar 2016: the last business day of the second month before.

RULE, written before the run
  D0 calendar check (plumbing): basis = Yahoo BZ=F - FRED spot. The mean
     |daily change in basis| on the first common day after each calendar
     expiry is >= 2x the median on all other days, in each era (expiries to
     Jan 2016 old rule; Mar 2016 contract on, new rule). Otherwise stop: the
     labels are not trusted and nothing below is read.
  Statistic: as research/verdict_ci.py (moving-block bootstrap, 90% CI), on
     nowcast_in_adl.py's per-week rows from the 2026-11-05 archive,
     adl_ecm_nc against adl_ecm.
  D1 non-roll weeks support the nowcast if the CI's upper end is < 1 for
     every fuel at h = 1..3 in non-crisis weeks, and < 1.05 in crisis weeks.
  D2 roll weeks, both regimes together (the regime is not known at forecast
     time), Diesel + Regular pooled, h = 1 and 2:
       "worse" at either horizon (lower end > 1) -> fall back to adl_ecm in
         roll weeks;
       "better" at both (upper end < 1) -> no fallback;
       otherwise not detectable -> no fallback by default, roll weeks open.

PREDICTIONS, written before the run (pooled D+R, non-crisis)
  P1 non-roll weeks gain at least as much as all weeks, at every h.
  P2 roll weeks gain less than non-roll weeks, at h = 1 and 2.
  P3 in roll weeks the nowcast still does not lose (point ratio <= 1), every h.
  P4 hence falling back in roll weeks is worse than the nowcast over all weeks.

    python research/verdict_ci.py     # first: writes the per-week rows
    python research/roll_weeks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.easter import easter

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "research"))

import verdict_ci as vc                  # noqa: E402

RESULTS = ROOT / "data" / "verdict_ci" / "data" / "nowcast_results.csv"
YAHOO = ROOT / "data" / "brent_daily_yahoo.csv"
FRED = ROOT / "data" / "brent_daily.csv"
OUT = ROOT / "data" / "roll_weeks"
FUELS3 = (*vc.FUELS, "Premium Petrol 95R")
LAST_OLD_RULE = pd.Period("2016-02", "M")


def uk_holidays(y0: int, y1: int) -> set[pd.Timestamp]:
    """The England and Wales holidays that can move an expiry date."""
    hol = set()
    for y in range(y0, y1 + 1):
        e = pd.Timestamp(easter(y))
        mondays = lambda m: pd.date_range(f"{y}-{m:02d}-01", periods=31, freq="D")  # noqa: E731
        may = [d for d in mondays(5) if d.month == 5 and d.dayofweek == 0]
        aug = [d for d in mondays(8) if d.month == 8 and d.dayofweek == 0]
        hol |= {e - pd.Timedelta(days=2), e + pd.Timedelta(days=1), may[0], may[-1], aug[-1]}
    return hol


HOL = uk_holidays(2010, 2028)


def is_bday(d: pd.Timestamp) -> bool:
    return d.dayofweek < 5 and d not in HOL


def prev_bday(d: pd.Timestamp) -> pd.Timestamp:
    d = d - pd.Timedelta(days=1)
    while not is_bday(d):
        d -= pd.Timedelta(days=1)
    return d


def old_rule(contract: pd.Period) -> pd.Timestamp:
    d15 = contract.start_time - pd.Timedelta(days=15)
    if not is_bday(d15):
        d15 = prev_bday(d15)
    return prev_bday(d15)


def new_rule(contract: pd.Period) -> pd.Timestamp:
    return prev_bday((contract - 1).start_time)     # last business day of month - 2


def expiry(contract: pd.Period) -> pd.Timestamp:
    return old_rule(contract) if contract <= LAST_OLD_RULE else new_rule(contract)


EXPIRIES = pd.Series({c: expiry(c) for c in pd.period_range("2012-12", "2027-04", freq="M")})


def calendar_check() -> bool:
    y = pd.read_csv(YAHOO, parse_dates=["date"]).set_index("date").close
    f = pd.read_csv(FRED, parse_dates=["date"]).set_index("date").brent_usd_bbl
    b = pd.concat([y, pd.to_numeric(f, errors="coerce")], axis=1, join="inner").dropna()
    b = b[b.index >= "2012-12-01"]
    db = (b.iloc[:, 0] - b.iloc[:, 1]).diff().abs().dropna()
    days = db.index.to_numpy()
    ok = True
    print("D0 calendar check: mean |change in basis| on the day after an expiry, / median elsewhere")
    for era, sel in (("old rule", EXPIRIES.index <= LAST_OLD_RULE),
                     ("new rule", EXPIRIES.index > LAST_OLD_RULE)):
        ex = EXPIRIES[sel]
        ex = ex[(ex > db.index[0]) & (ex < db.index[-1])]
        after = pd.DatetimeIndex(days[np.searchsorted(days, ex.to_numpy(), side="right")])
        other = db[~db.index.isin(after)]
        ratio = db[after].mean() / other.median()
        # the other era's rule, applied to this era's months, as a placebo
        placebo = pd.Series({c: new_rule(c) if c <= LAST_OLD_RULE else old_rule(c)
                             for c in ex.index})
        placebo = placebo[(placebo > db.index[0]) & (placebo < db.index[-1])]
        pa =pd.DatetimeIndex(days[np.searchsorted(days, placebo.to_numpy(), side="right")])
        pratio = db[pa].mean() / other.median()
        print(f"  {era}: {len(ex)} expiries, ratio {ratio:.2f}  (placebo, other era's rule: {pratio:.2f})")
        ok &= ratio >= 2
    print(f"  -> {'PASS' if ok else 'FAIL: labels not trusted, stop'}\n")
    return ok


def label(dates: pd.Series) -> pd.Series:
    e = np.sort(EXPIRIES.to_numpy())
    mon = (dates - pd.Timedelta(days=4)).to_numpy()
    wed = (dates + pd.Timedelta(days=5)).to_numpy()
    return pd.Series(np.searchsorted(e, wed, side="left") > np.searchsorted(e, mon, side="left"),
                     index=dates.index)


def main() -> int:
    if not calendar_check():
        return 1
    r = pd.read_csv(RESULTS, parse_dates=["date"])
    r = r[r.outcome_known.astype(str).str.lower().eq("true")].copy()
    r["hi"] = r.hi.astype(str).str.lower().eq("true")
    r["roll"] = label(r.date)
    r["fallback"] = np.where(r.roll, r.adl_ecm, r.adl_ecm_nc)
    wk = r.drop_duplicates("date")
    print(f"origins {len(wk)}, roll weeks {wk.roll.sum()} ({wk.roll.mean():.0%})\n")

    rows = []

    def add(test, regime, split, frame, var, base):
        for fuel in (*FUELS3, "pooled D+R"):
            sub = frame[frame.fuel.isin(vc.FUELS)] if fuel == "pooled D+R" else frame[frame.fuel == fuel]
            for h in (1, 2, 3):
                n, p, lo, hi = vc.ratio_ci(sub[sub.h == h], var, base)
                rows.append(dict(test=test, regime=regime, split=split, fuel=fuel, h=h, n=n,
                                 change=(p - 1) * 100, ci_lo=(lo - 1) * 100, ci_hi=(hi - 1) * 100))

    for regime, sub in (("non-crisis", r[~r.hi]), ("crisis", r[r.hi]), ("all", r)):
        for split, s in (("all weeks", sub), ("non-roll", sub[~sub.roll]), ("roll", sub[sub.roll])):
            add("nowcast vs adl_ecm", regime, split, s, "adl_ecm_nc", "adl_ecm")
        add("fallback vs nowcast", regime, "all weeks", sub, "fallback", "adl_ecm_nc")
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "roll_weeks.csv", index=False)

    pd.set_option("display.width", 200)
    pool = out[out.fuel == "pooled D+R"]
    print("Pooled D+R, MAE change %, 90% CI (negative = first named is better)")
    print(pool.round(1).to_string(index=False))

    nr = out[(out.split == "non-roll") & (out.test == "nowcast vs adl_ecm") & out.fuel.isin(FUELS3)]
    d1 = (nr[nr.regime == "non-crisis"].ci_hi < 0).all() and (nr[nr.regime == "crisis"].ci_hi < 5).all()
    rl = pool[(pool.split == "roll") & (pool.regime == "all") & (pool.h <= 2)]
    d2 = ("worse" if (rl.ci_lo > 0).any() else "better" if (rl.ci_hi < 0).all() else "not detectable")
    print(f"\nD1 non-roll weeks support the nowcast: {'YES' if d1 else 'NO'}")
    print(nr.pivot_table(index=["regime", "fuel"], columns="h", values="ci_hi").round(1).to_string())
    print(f"D2 roll weeks: {d2}")

    nc = pool[pool.regime == "non-crisis"].set_index(["test", "split", "h"]).change
    t = "nowcast vs adl_ecm"
    p1 = all(nc[(t, "non-roll", h)] <= nc[(t, "all weeks", h)] for h in (1, 2, 3))
    p2 = all(nc[(t, "roll", h)] > nc[(t, "non-roll", h)] for h in (1, 2))
    p3 = all(nc[(t, "roll", h)] <= 0 for h in (1, 2, 3))
    p4 = all(nc[("fallback vs nowcast", "all weeks", h)] > 0 for h in (1, 2, 3))
    print(f"\nPredictions: P1 {'held' if p1 else 'MISSED'}, P2 {'held' if p2 else 'MISSED'}, "
          f"P3 {'held' if p3 else 'MISSED'}, P4 {'held' if p4 else 'MISSED'}")
    print(f"-> {OUT / 'roll_weeks.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
