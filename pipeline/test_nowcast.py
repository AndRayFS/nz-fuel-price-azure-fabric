"""Plumbing for W23 step 2: pipeline/nowcast.py against the research it ports.

The gate (docs/workstreams.md, W23): on the 5 Nov 2026 archive, `adl_ecm_nc`
from nowcast.py agrees with research/nowcast_in_adl.py to 0.0001 c/L at
every origin, fuel and horizon, for three days and for two.

The inputs are fixed, so that only the code differs:

  the panel   rebuilt from the archive: `weekly_prices.csv`, with the regime
              columns from `forecasts.csv`. Checked first — backtest.py on the
              rebuilt panel reproduces the archive's `pred_adl_ecm` — so it is
              the panel that load ran on.
  Yahoo       BZ=F and NZDUSD=X daily, fetched once. Each side converts the
              same bytes with its own code: research through its own
              `yahoo_daily`, served the saved bytes in place of the network.

Before those, the parts research never had: the expiry calendar against
research/roll_weeks.py, and the window — which days come from the contract
by symbol, which from BZ=F, which FX the run day takes — on synthetic cases,
as test_gate.py does for the gate.

No pytest (see test_gate.py). Run it with `python pipeline/test_nowcast.py`;
it prints one line per check and exits non-zero on the first failure. It
downloads the archive (public, about 0.6 MB) and two Yahoo series into a
temporary directory. Nothing touches the warehouse, and nothing under data/
is written.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

import backtest as bt
import nowcast as nc

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "research"))     # compared against, never imported by nowcast.py

ARCHIVE = "https://nzfueldata.blob.core.windows.net/data/2026-11-05/nz-fuel-2026-11-05.zip"
TOL = 1e-4                                       # c/L


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


# --- offline: the calendar and the window ------------------------------------

def check_calendar() -> None:
    import roll_weeks as rw
    want = {c: e.date() for c, e in rw.EXPIRIES.items() if c >= pd.Period("2016-03", "M")}
    bad = [c for c, e in want.items() if nc.expiry(c.year, c.month) != e]
    check("expiry calendar matches research/roll_weeks.py", not bad,
          f"{len(want)} contracts, Mar 2016 - Apr 2027" + (f"; differs at {bad[:3]}" if bad else ""))
    cases = {dt.date(2026, 11, 8): "BZF27.NYM", dt.date(2026, 11, 30): "BZF27.NYM",
             dt.date(2026, 12, 1): "BZG27.NYM", dt.date(2027, 1, 1): "BZH27.NYM"}
    got = {d: nc.symbol(*nc.contract_on(d)) for d in cases}
    check("front contract on the day, expiry day included", got == cases, str(got))


def _series(days, base: float) -> pd.Series:
    idx = pd.DatetimeIndex(days)
    return pd.Series(base + np.arange(len(idx), dtype=float), index=idx)


def check_window() -> None:
    bdays = pd.bdate_range("2026-10-26", "2026-12-04")
    bz = _series(bdays, 100.0)                   # BZ=F daily: 100, 101, ...

    # No expiry inside the window: every window day by symbol, the rest BZ=F.
    run, last = pd.Timestamp("2026-11-18"), pd.Timestamp("2026-11-13")
    sym = _series(pd.bdate_range("2026-11-02", "2026-11-18"), 200.0)
    usd, prov = nc.window_usd(bz, sym, last - pd.Timedelta(days=4), run)
    win = usd["2026-11-09":"2026-11-18"]
    check("no roll: window days come from the contract by symbol",
          (win == sym["2026-11-09":"2026-11-18"]).all() and (prov.usd_source == "by symbol").all()
          and set(prov.contract) == {"BZF27.NYM"})
    check("no roll: days before the window stay BZ=F, even where the symbol has them",
          (usd[:"2026-11-06"] == bz[:"2026-11-06"]).all())

    # A roll week: BZF27 expires Monday 30 Nov, the run is Wednesday 2 Dec.
    run, last = pd.Timestamp("2026-12-02"), pd.Timestamp("2026-11-27")
    sym = _series(pd.bdate_range("2026-11-16", "2026-12-02"), 300.0)    # BZG27
    usd, prov = nc.window_usd(bz, sym, last - pd.Timedelta(days=4), run)
    old = prov[pd.to_datetime(prov.date) <= "2026-11-30"]
    new = prov[pd.to_datetime(prov.date) > "2026-11-30"]
    check("roll week: days to the expiry are BZ=F, on the expired contract",
          (old.usd_source == "BZ=F daily").all() and set(old.contract) == {"BZF27.NYM"}
          and (usd["2026-11-23":"2026-11-30"] == bz["2026-11-23":"2026-11-30"]).all(),
          f"{len(old)} days")
    check("roll week: days after it are the new front by symbol",
          (new.usd_source == "by symbol").all() and set(new.contract) == {"BZG27.NYM"}
          and (usd["2026-12-01":"2026-12-02"] == sym["2026-12-01":"2026-12-02"]).all(),
          f"{len(new)} days")

    # A day the symbol lacks is missing, never filled from BZ=F.
    run, last = pd.Timestamp("2026-11-18"), pd.Timestamp("2026-11-13")
    sym = _series(pd.bdate_range("2026-11-02", "2026-11-18"), 200.0).drop(pd.Timestamp("2026-11-17"))
    usd, _ = nc.window_usd(bz, sym, last - pd.Timedelta(days=4), run)
    check("a day missing by symbol stays missing", pd.Timestamp("2026-11-17") not in usd.index)

    # Expiry on the run day: the contract still trades, so it is still by symbol.
    run, last = pd.Timestamp("2026-11-30"), pd.Timestamp("2026-11-27")
    sym = _series(pd.bdate_range("2026-11-16", "2026-11-30"), 200.0)
    _, prov = nc.window_usd(bz, sym, last - pd.Timedelta(days=4), run)
    check("expiry on the run day: still by symbol",
          (prov.usd_source == "by symbol").all() and set(prov.contract) == {"BZF27.NYM"})

    # FX: the run day takes the latest hourly price, present or not.
    fx = pd.Series([0.55, 0.56], index=pd.DatetimeIndex(["2026-11-17", "2026-11-18"]))
    got = nc.with_run_day(fx, 0.57, pd.Timestamp("2026-11-18"))
    check("FX: the run day's daily bar is replaced by the hourly price",
          got["2026-11-18"] == 0.57 and got["2026-11-17"] == 0.55)
    got = nc.with_run_day(fx.iloc[:1], 0.57, pd.Timestamp("2026-11-18"))
    check("FX: the run day is added when it has no daily bar", got["2026-11-18"] == 0.57)


# --- offline: the guard -------------------------------------------------------

def _case(run: str, last: str, sym_from: str, *, bst: bool = False,
          hourly: bool = True) -> tuple[nc.Fetched, pd.Timestamp, pd.Timestamp]:
    """A run with every series complete and quiet. BZ=F and the contract by
    symbol differ by about ten dollars, so BZ=F is never mistaken for it."""
    run_, last_ = pd.Timestamp(run), pd.Timestamp(last)
    bdays = pd.bdate_range(last_ - pd.Timedelta(days=25), run_)
    sdays = pd.bdate_range(sym_from, run_)
    fdays = bdays[(bdays.dayofweek != 4) & (bdays != run_)] if bst else bdays
    f = nc.Fetched(front=nc.symbol(*nc.contract_on(run_.date())),
                   bz=pd.Series(100 + 0.1 * np.arange(len(bdays)), index=bdays),
                   by_symbol=pd.Series(90 + 0.1 * np.arange(len(sdays)), index=sdays),
                   fx_daily=pd.Series(0.6, index=fdays))
    if hourly:
        f.hourly = pd.Series([0.6], index=pd.DatetimeIndex([run_ + pd.Timedelta(hours=19)], tz="UTC"))
    else:
        f.errors["hourly"] = "URLError: test"
    return f, last_, run_


def check_guard() -> None:
    plain = ("2026-11-18", "2026-11-13", "2026-11-02")       # GMT, no roll, front BZF27
    wed, tue = pd.Timestamp("2026-11-18"), pd.Timestamp("2026-11-17")

    d = nc.guard(*_case(*plain))
    check("guard: everything there, three days", d.days == 3 and not d.reasons, d.label)

    f, last, run = _case(*plain)
    f.bz, f.by_symbol = f.bz.drop(wed), f.by_symbol.drop(wed)
    d = nc.guard(f, last, run)
    check("guard: Wednesday's bar late, two days", d.days == 2, "; ".join(d.reasons))

    f, last, run = _case(*plain)
    f.by_symbol = f.by_symbol.drop(tue)
    d = nc.guard(f, last, run)
    check("guard: Tuesday missing by symbol but traded, adl_ecm", d.days == 0, "; ".join(d.reasons))

    f, last, run = _case(*plain)
    f.bz, f.by_symbol = f.bz.drop(tue), f.by_symbol.drop(tue)
    d = nc.guard(f, last, run)
    check("guard: Tuesday in neither series is a holiday, three days", d.days == 3, d.label)

    f, last, run = _case(*plain)
    f.by_symbol.loc["2026-11-16"] *= 1.4
    d = nc.guard(f, last, run)
    check("guard: a Brent move above the record, adl_ecm",
          d.days == 0 and any("above 0.3" in r for r in d.reasons), d.reasons[0] if d.reasons else "")

    f, last, run = _case(*plain)
    f.fx_daily.loc["2026-11-16"] *= 1.09
    d = nc.guard(f, last, run)
    check("guard: an FX move above the record, adl_ecm",
          d.days == 0 and any("above 0.08" in r for r in d.reasons), d.reasons[0] if d.reasons else "")

    f, last, run = _case(*plain)
    f.fx_daily = f.fx_daily.drop(tue)
    d = nc.guard(f, last, run)
    check("guard: a gap in FX history is skipped as the backtest skips it, three days",
          d.days == 3 and any("no FX bar" in n for n in d.notes), d.notes[0] if d.notes else "")

    f, last, run = _case(*plain)
    f.fx_daily = f.fx_daily[:"2026-11-12"]
    d = nc.guard(f, last, run)
    check("guard: FX daily stops short of the run, adl_ecm",
          d.days == 0 and any("stale" in r for r in d.reasons), d.reasons[0] if d.reasons else "")

    f, last, run = _case(*plain)
    f.by_symbol, f.errors["by_symbol"] = None, "HTTPError: HTTP Error 404: Not Found"
    d = nc.guard(f, last, run)
    check("guard: the contract by symbol answers 404, adl_ecm", d.days == 0, d.reasons[0])

    d = nc.guard(*_case(*plain, hourly=False))
    check("guard: no hourly FX under GMT, the run day's daily bar serves, three days",
          d.days == 3 and d.notes, d.notes[0])

    bst = ("2027-06-16", "2027-06-11", "2027-06-01")         # BST, front BZQ27
    d = nc.guard(*_case(*bst, bst=True))
    check("guard: under BST, Fridays without FX are not missing, three days", d.days == 3, d.label)
    d = nc.guard(*_case(*bst, bst=True, hourly=False))
    check("guard: under BST without hourly FX, Wednesday has none, two days",
          d.days == 2, "; ".join(d.reasons))

    f, last, run = _case("2030-06-19", "2030-06-14", "2030-06-03", bst=True)
    j = pd.Timestamp("2030-06-19")
    f.bz, f.by_symbol = f.bz.drop(j), f.by_symbol.drop(j)
    d = nc.guard(f, last, run)
    check("guard: a Wednesday that is a fixed US holiday, three days", d.days == 3, d.label)

    roll = ("2026-12-02", "2026-11-27", "2026-11-16")         # BZF27 expired 30 Nov
    d = nc.guard(*_case(*roll))
    check("guard: roll week, BZ=F rewritten to the expired contract, three days",
          d.days == 3, d.label)
    f, last, run = _case(*roll)
    old = pd.bdate_range("2026-11-23", "2026-11-30")
    f.bz.loc[old] = f.by_symbol.loc[old].to_numpy()
    d = nc.guard(f, last, run)
    check("guard: roll week, BZ=F still the next contract, adl_ecm",
          d.days == 0 and sum("still shows the next contract" in r for r in d.reasons) == len(old),
          f"{len(d.reasons)} days flagged")


# --- the archive ----------------------------------------------------------------

def rebuild_panel(tmp: Path) -> Path:
    src = tmp / "archive"
    with urllib.request.urlopen(ARCHIVE, timeout=60) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(src)
    w = pd.read_csv(src / "weekly_prices.csv").rename(columns={"week_date": "Date", "fuel": "Fuel"})
    w.to_csv(tmp / "panel_weekly.csv", index=False)
    f = pd.read_csv(src / "forecasts.csv")
    flags = f[["week_date", "fuel", "crude_vol_regime", "crude_episode_id",
               "crude_move_regime"]].drop_duplicates(["week_date", "fuel"])
    flags.to_csv(tmp / "period_flags.csv", index=False)
    bt.PANEL, bt.FLAGS = tmp / "panel_weekly.csv", tmp / "period_flags.csv"
    return src


def check_rebuild(src: Path) -> None:
    a = pd.read_csv(src / "forecasts.csv", parse_dates=["week_date"]).dropna(subset=["pred_adl_ecm"])
    worst, n, missing = 0.0, 0, 0
    for fuel in nc.FUELS:
        d = bt.load(fuel)
        retail = d.adjusted_retail_price.to_numpy()
        got = {}
        for t in range(bt.MIN_TRAIN, len(d)):
            b = bt.fit_adl(d, t + 1, with_ecm=True)
            if b is None:
                continue
            for h in bt.HORIZONS:
                e = bt.adl_forecast(d, t, b, h, True)
                if np.isfinite(e):
                    got[(d.index[t], h)] = retail[t] + e * 1.15
        for r in a[a.fuel == fuel].itertuples():
            v = got.get((r.week_date, r.horizon_weeks))
            if v is None:
                missing += 1
                continue
            worst, n = max(worst, abs(v - r.pred_adl_ecm)), n + 1
    check("rebuilt panel reproduces the archive's pred_adl_ecm",
          missing == 0 and worst <= TOL, f"{n} rows, max |diff| {worst:.2e} c/L, {missing} missing")


# --- against research -----------------------------------------------------------

def research_results(tmp: Path, saved: dict[str, bytes], days: int) -> pd.DataFrame:
    import nowcast_brent
    import nowcast_in_adl

    def urlopen(req, timeout=None):
        return io.BytesIO(saved[req.full_url])     # KeyError if research asks for another URL

    root = tmp / f"research_{days}"
    (root / "data").mkdir(parents=True)
    nowcast_brent.ROOT = root                      # its Yahoo cache, served from `saved`
    nowcast_in_adl.ROOT = root                     # its --save path
    sink = io.StringIO()
    with mock.patch.object(urllib.request, "urlopen", urlopen), \
            mock.patch.object(sys, "argv", ["nowcast_in_adl", "--days", str(days), "--save"]), \
            contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        nowcast_in_adl.main()
    return pd.read_csv(root / "data" / "nowcast_results.csv", parse_dates=["date"])


def check_against_research(tmp: Path) -> None:
    import nowcast_brent
    urls = {s: nc.chart_url(s, "1d", nc.HISTORY_FROM) for s in ("BZ=F", "NZDUSD=X")}
    saved = {u: nc.get(u) for u in urls.values()}
    cpl = nc.brent_nzd_cpl(nc.daily(nc.parse_chart(saved[urls["BZ=F"]])),
                           nc.daily(nc.parse_chart(saved[urls["NZDUSD=X"]])))

    for days in (3, 2):
        res = research_results(tmp, saved, days)
        if days == 3:
            theirs = nowcast_brent.brent_nzd_cpl()             # from the cache research just wrote
            both = pd.concat([cpl.rename("a"), theirs.rename("b")], axis=1)
            diff = (both.a - both.b).abs().max()
            check("Brent in NZ c/L matches research, day for day",
                  both.notna().all().all() and diff <= 1e-9,
                  f"{len(both)} days, {both.index.min():%Y-%m-%d} to {both.index.max():%Y-%m-%d}, "
                  f"max |diff| {diff:.1e}")

        rows = []
        for fuel in nc.FUELS:
            d = bt.load(fuel)
            x = nc.features(cpl, d.index)[f"x{days}"].to_numpy()
            y, fin = d.d_cost.to_numpy(), d.is_final.to_numpy()
            for t in range(bt.MIN_TRAIN, len(d)):
                b = bt.fit_adl(d, t + 1, with_ecm=True)
                if b is None:
                    continue
                v = nc.nowcast_at(x, y, fin, t)
                for h in bt.HORIZONS:
                    e = nc.forecast_with_nowcast(d, t, b, h, True, v) if np.isfinite(v) else np.nan
                    rows.append((fuel, d.index[t], h, e * 1.15 if np.isfinite(e) else np.nan))
        mine = pd.DataFrame(rows, columns=["fuel", "date", "h", "mine"])
        m = res.merge(mine, on=["fuel", "date", "h"], how="outer", indicator=True)
        unmatched = (m._merge != "both").sum()
        a, b = m.adl_ecm_nc.to_numpy(), m.mine.to_numpy()
        nan_mismatch = (np.isfinite(a) != np.isfinite(b)).sum()
        fin_ = np.isfinite(a) & np.isfinite(b)
        worst = np.abs(a[fin_] - b[fin_]).max()
        check(f"adl_ecm_nc on {days} days matches research to {TOL} c/L",
              unmatched == 0 and nan_mismatch == 0 and worst <= TOL,
              f"{fin_.sum()} forecasts, max |diff| {worst:.1e} c/L, "
              f"{nan_mismatch} missing on one side only, {unmatched} unmatched rows")


def main() -> int:
    check_calendar()
    check_window()
    check_guard()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = rebuild_panel(tmp)
        check_rebuild(src)
        check_against_research(tmp)
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
