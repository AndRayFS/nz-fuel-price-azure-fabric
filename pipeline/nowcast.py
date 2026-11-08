"""The nowcast in production — W23, step 2, 8 Nov 2026.

What it is. Brent in NZ cents per litre over Monday to Wednesday of the week
in progress, against its mean over the week before:

    x(t+1) = m3(t+1) - m5(t)

regressed on MBIE's `d_cost` over Final weeks up to t, and applied to week
t+1, which MBIE has not published yet. That estimate enters the ADL+ECM as
index t+1 (`forecast_with_nowcast`). The method and its record are in
docs/research.md, from "The nowcast survives the walk-forward test"
(8 Sep 2026) on. This file is research/nowcast_in_adl.py and
research/nowcast_brent.py ported out of research/, with nothing changed in
the arithmetic.

The same feature on two days, Monday and Tuesday, sits beside it. It is the
guard's fallback when Wednesday is missing (docs/research.md, 8 Nov 2026), and
it is its own regression, not the three-day one given fewer days.

Three sources, because Yahoo's `BZ=F` is two series (docs/research.md,
"Yahoo's Brent rolls twice", 7 Nov 2026):

  history     `BZ=F` daily: settlements, on the calendar front contract,
              switching on its expiry. The series the backtest was scored on.
  the window  Monday of week t to the run, from the calendar front contract
              by symbol (`BZF27.NYM` until 30 Nov 2026). `BZ=F`'s live view
              moves to the next contract 4-9 trading days early, and its daily
              bars for those days have been read as the next contract and
              rewritten later. A window day on a contract that has expired by
              the run cannot be had by symbol (404); it comes from `BZ=F` and
              is marked so, for the guard.
  FX          `NZDUSD=X` daily as backtested — one price at midnight London,
              dated by UTC — except the run day, which takes the latest
              hourly price.

Plumbing: `pipeline/test_nowcast.py` checks this file against the research it
ports, on the 5 Nov 2026 archive, to 0.0001 c/L.

Not here yet: the guard (W23 step 3) and the forecast column (step 4).
Nothing in the weekly chain calls this file.

Usage:  python pipeline/nowcast.py
Reads data/panel_weekly.csv and data/period_flags.csv as backtest.py does,
fetches from Yahoo, prints the window and each fuel's estimate for the week
in progress, and writes the window to data/nowcast_window.csv. No warehouse,
no capacity.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt

ROOT = Path(__file__).parents[1]
WINDOW_CSV = ROOT / "data" / "nowcast_window.csv"

# Yahoo's chart endpoint, undocumented, the request research/nowcast_brent.py
# makes: same host, path and User-Agent. HISTORY_FROM is its period1.
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?period1={p1}&period2=9999999999&interval={interval}")
HISTORY_FROM = 1104537600           # 1 Jan 2005
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 60

LITRES_PER_BBL = 158.987
NC_MIN_TRAIN = 52                   # as research/nowcast_in_adl.py
DAYS = (2, 3)
FUELS = ("Diesel", "Regular Petrol", "Premium Petrol 95R")
MONTH_CODE = "FGHJKMNQUVXZ"


# --- the expiry calendar -----------------------------------------------------
# ICE Brent, which NYMEX BZ follows, from the March 2016 contract: the last
# London business day of the second month before the contract month. The rule
# is research/roll_weeks.new_rule without pandas; test_nowcast.py checks the two
# agree on every contract from March 2016 to April 2027. As there, only the
# holidays that can end a month count. pipeline/probe_yahoo.py carries a copy,
# and goes when the probe does.

def _easter(y: int) -> dt.date:
    """Western Easter Sunday, by the anonymous Gregorian algorithm."""
    a = y % 19
    b, c = divmod(y, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(y, month, day + 1)


def _mondays(y: int, month: int) -> list[dt.date]:
    n = calendar.monthrange(y, month)[1]
    return [dt.date(y, month, d) for d in range(1, n + 1)
            if dt.date(y, month, d).weekday() == 0]


def _uk_holidays(y: int) -> set[dt.date]:
    e = _easter(y)
    return {e - dt.timedelta(days=2), e + dt.timedelta(days=1),
            _mondays(y, 5)[0], _mondays(y, 5)[-1], _mondays(y, 8)[-1]}


def expiry(year: int, month: int) -> dt.date:
    """Last trading day of the contract for `month` of `year`."""
    y, m = (year, month - 2) if month > 2 else (year - 1, month + 10)
    d = dt.date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5 or d in _uk_holidays(d.year):
        d -= dt.timedelta(days=1)
    return d


def _step(y: int, m: int, k: int) -> tuple[int, int]:
    n = y * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


def contract_on(day: dt.date) -> tuple[int, int]:
    """The calendar front contract on `day`: the first whose expiry is `day` or
    later. On its last trading day a contract still trades, and settles, as
    the front."""
    y, m = day.year, day.month
    while expiry(y, m) < day:
        y, m = _step(y, m, 1)
    return y, m


def symbol(y: int, m: int) -> str:
    return f"BZ{MONTH_CODE[m - 1]}{y % 100:02d}.NYM"


# --- Yahoo ---------------------------------------------------------------------

def chart_url(sym: str, interval: str, period1: int) -> str:
    return CHART.format(sym=sym, p1=period1, interval=interval)


def get(url: str) -> bytes:
    """One request. Raises on anything but an answer: an HTTP error (an expired
    symbol answers 404), a timeout, a refused connection."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def parse_chart(body: bytes) -> pd.Series:
    """Closes by UTC timestamp. Empty bars (null close) are dropped."""
    res = json.loads(body)["chart"]["result"][0]
    s = pd.Series(res["indicators"]["quote"][0]["close"],
                  index=pd.to_datetime(res["timestamp"], unit="s", utc=True),
                  dtype=float)
    return s.dropna()


def daily(closes: pd.Series) -> pd.Series:
    """Daily closes keyed by UTC date, which is how
    research/nowcast_brent.yahoo_daily dates them."""
    s = closes.copy()
    s.index = s.index.tz_convert("UTC").tz_localize(None).normalize()
    s = s[~s.index.duplicated(keep="last")]
    return s.sort_index().rename("close")


# --- the feature ---------------------------------------------------------------

def brent_nzd_cpl(usd: pd.Series, nzdusd: pd.Series) -> pd.Series:
    """Brent in NZ cents per litre, on the days both legs have a price.

    A day missing from one is missing from the other rather than silently
    mismatched. In UK summer that drops Friday — NZDUSD=X has no bar dated
    Friday then — so a week's mean runs Monday to Thursday, as in the backtest.
    """
    both = pd.concat([usd.rename("usd"), nzdusd.rename("nzdusd")],
                     axis=1, sort=True).dropna()
    return (both.usd / both.nzdusd) * 100.0 / LITRES_PER_BBL


def week_means(cpl: pd.Series, stamps: pd.DatetimeIndex,
               ks: tuple[int, ...] = (2, 3, 5)) -> pd.DataFrame:
    """Mean of the first k weekdays of each stamped week.

    A stamp is the Friday on the fifth day of its week, so Monday is the stamp
    less four days. A day with no price — a holiday — is skipped, not filled:
    the mean is over the trading days that existed.
    """
    out = {}
    for k in ks:
        vals = []
        for f in stamps:
            lo, hi = f - pd.Timedelta(days=4), f - pd.Timedelta(days=5 - k)
            window = cpl.loc[(cpl.index >= lo) & (cpl.index <= hi)]
            vals.append(window.mean() if len(window) else np.nan)
        out[f"m{k}"] = vals
    return pd.DataFrame(out, index=stamps)


def features(cpl: pd.Series, stamps: pd.DatetimeIndex) -> pd.DataFrame:
    """x2 and x3 at each stamp: the first two or three days of that week
    against the whole week before it."""
    m = week_means(cpl, stamps)
    return pd.DataFrame({f"x{k}": m[f"m{k}"] - m.m5.shift(1) for k in DAYS},
                        index=stamps)


def nowcast_at(x: np.ndarray, y: np.ndarray, is_final: np.ndarray, t: int) -> float:
    """Week t+1's `d_cost`, from its partial reading `x[t+1]`.

    The regression is refit on the Final weeks up to and including t, never
    later: MBIE publishes week t on the Wednesday after it ends, and by then
    Monday to Wednesday of week t+1 have traded. `x` may be one longer than
    `y`, its last element the week in progress.
    """
    if t + 1 >= len(x) or not np.isfinite(x[t + 1]):
        return np.nan
    xs, ys, fs = x[:t + 1], y[:t + 1], is_final[:t + 1]
    ok = np.isfinite(xs) & np.isfinite(ys) & fs
    if ok.sum() < NC_MIN_TRAIN:
        return np.nan
    A = np.column_stack([np.ones(ok.sum()), xs[ok]])
    g = np.linalg.lstsq(A, ys[ok], rcond=None)[0]
    return g[0] + g[1] * x[t + 1]


def forecast_with_nowcast(d: pd.DataFrame, t: int, beta: np.ndarray, h: int,
                          with_ecm: bool, nc: float) -> float:
    """`backtest.adl_forecast`, with index t+1 supplied by the nowcast.

    The one change is the lag range, k >= j - 1 rather than k >= j: k = j - 1
    lands on t+1, the week in progress, which is what the nowcast supplies. It
    reaches every horizon — `b0` at h=1, `b1` at h=2, `b2` at h=3.
    """
    dc = d.d_cost.to_numpy()
    total = 0.0
    for j in range(1, h + 1):
        step = beta[0]
        for k in range(max(0, j - 1), bt.K + 1):
            idx = t + j - k
            val = nc if idx == t + 1 else (dc[idx] if idx <= t else np.nan)
            if idx < 0 or not np.isfinite(val):
                return np.nan
            step += beta[1 + k] * val
        if with_ecm:
            dev = d.dev.to_numpy()[t]
            if not np.isfinite(dev):
                return np.nan
            step += beta[-1] * dev
        total += step
    return total


# --- the window at the run -----------------------------------------------------

def window_usd(bz: pd.Series, by_symbol: pd.Series, window_from: pd.Timestamp,
               run_date: pd.Timestamp) -> tuple[pd.Series, pd.DataFrame]:
    """Daily Brent in USD, with the window taken from the contract by symbol.

    `bz` is BZ=F daily and `by_symbol` the run day's calendar front contract,
    both keyed by UTC date. Window days on that contract — every window day
    after the last expiry before the run — come from `by_symbol` only: a day it
    lacks stays missing and is never filled from `bz`, whose bar for it may be
    the next contract. Window days on a contract that has expired by the run
    come from `bz`. Returns the series and one row per window day saying where
    its price came from.
    """
    fy, fm = contract_on(run_date.date())
    last_expiry = pd.Timestamp(expiry(*_step(fy, fm, -1)))
    live_from = max(window_from, last_expiry + pd.Timedelta(days=1))

    keep = ~((bz.index >= live_from) & (bz.index <= run_date))
    live = by_symbol[(by_symbol.index >= live_from) & (by_symbol.index <= run_date)]
    usd = pd.concat([bz[keep], live]).sort_index().rename("usd")

    win = usd[(usd.index >= window_from) & (usd.index <= run_date)]
    rows = [dict(date=day.date(), contract=symbol(*contract_on(day.date())),
                 usd_source="by symbol" if day >= live_from else "BZ=F daily",
                 usd=price)
            for day, price in win.items()]
    return usd, pd.DataFrame(rows, columns=["date", "contract", "usd_source", "usd"])


def with_run_day(fx_daily: pd.Series, latest: float,
                 run_date: pd.Timestamp) -> pd.Series:
    """NZDUSD=X daily as backtested, the run day's price replaced by the
    latest hourly one. In UK summer the run day has no daily bar yet; in UK
    winter it has one carrying the day before's close."""
    fx = fx_daily.copy()
    fx.loc[run_date] = latest
    return fx.sort_index().rename("nzdusd")


def live_inputs(last_stamp: pd.Timestamp, run_date: pd.Timestamp,
                fetch=get) -> tuple[pd.Series, pd.DataFrame]:
    """Everything fetched at the run: the Brent series in NZ c/L, and the
    window's provenance. Raises if any request fails; the guard is step 3."""
    window_from = last_stamp - pd.Timedelta(days=4)
    bz = daily(parse_chart(fetch(chart_url("BZ=F", "1d", HISTORY_FROM))))
    fx_daily = daily(parse_chart(fetch(chart_url("NZDUSD=X", "1d", HISTORY_FROM))))
    front = symbol(*contract_on(run_date.date()))
    since = int((window_from - pd.Timedelta(days=7)).tz_localize("UTC").timestamp())
    by_symbol = daily(parse_chart(fetch(chart_url(front, "1d", since))))
    hourly = parse_chart(fetch(chart_url("NZDUSD=X", "60m", int(time.time()) - 2 * 86400)))

    usd, prov = window_usd(bz, by_symbol, window_from, run_date)
    fx = with_run_day(fx_daily, float(hourly.iloc[-1]), run_date)
    cpl = brent_nzd_cpl(usd, fx)

    days = pd.to_datetime(prov.date)
    prov["nzdusd"] = fx.reindex(days).to_numpy()
    prov["fx_source"] = np.where(
        days == run_date, f"hourly, {hourly.index[-1]:%Y-%m-%d %H:%M} UTC", "daily bar")
    prov["cpl"] = cpl.reindex(days).to_numpy()
    return cpl, prov


def main() -> int:
    run_date = pd.Timestamp(dt.datetime.now(dt.UTC).date())
    frames = {fuel: bt.load(fuel) for fuel in FUELS}
    last = max(d.index[-1] for d in frames.values())
    nxt = last + pd.Timedelta(days=7)

    cpl, prov = live_inputs(last, run_date)
    print(f"Run day {run_date:%a %d %b %Y} UTC. Panel ends {last:%d %b %Y}; "
          f"the week in progress is stamped {nxt:%d %b %Y}.\n")
    print(prov.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    print("\nEstimated d_cost for the week in progress, c/L (two days | three days):")
    for fuel, d in frames.items():
        X = features(cpl, d.index.append(pd.DatetimeIndex([nxt])))
        t = len(d) - 1
        y, fin = d.d_cost.to_numpy(), d.is_final.to_numpy()
        x = {k: X[f"x{k}"].to_numpy() for k in DAYS}
        nc = {k: nowcast_at(x[k], y, fin, t) for k in DAYS}
        print(f"  {fuel:<19} feature {x[2][-1]:+7.3f} | {x[3][-1]:+7.3f}"
              f"    estimate {nc[2]:+7.3f} | {nc[3]:+7.3f}")

    WINDOW_CSV.parent.mkdir(exist_ok=True)
    prov.to_csv(WINDOW_CSV, index=False)
    print(f"\nwindow written to {WINDOW_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
