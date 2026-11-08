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

The guard (W23 step 3) decides which of them the run may use: three days;
two, when Wednesday alone is missing; or none, plain `adl_ecm`, when a request
failed, another day is missing, a daily move exceeds anything in history, or a
roll-week day on BZ=F cannot be confirmed as the expired contract. Its rules
and the measurements behind them are with `guard`.

Plumbing: `pipeline/test_nowcast.py` checks this file against the research it
ports, on the 5 Nov 2026 archive, to 0.0001 c/L, and the guard on synthetic
cases.

Not here yet: the forecast column (step 4). Nothing in the weekly chain calls
this file.

Usage:  python pipeline/nowcast.py
Reads data/panel_weekly.csv and data/period_flags.csv as backtest.py does,
fetches from Yahoo, prints the window, the guard's decision and each fuel's
estimate for the week in progress, and writes the window to
data/nowcast_window.csv. No warehouse, no capacity.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

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
    """Closes by UTC timestamp. Empty bars (null close) are dropped.

    A range with no trading — the hourly FX over a weekend — comes back with
    no timestamps and an empty quote; that is an empty series, which the
    caller reports as "no bars", not a KeyError (seen 9 Nov 2026).
    """
    res = json.loads(body)["chart"]["result"][0]
    ts = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or [None] * len(ts)
    s = pd.Series(closes, index=pd.to_datetime(ts, unit="s", utc=True), dtype=float)
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


@dataclass
class Fetched:
    """What the run got from Yahoo. A series is None when its request failed,
    and `errors` says how."""
    front: str
    bz: pd.Series | None = None
    fx_daily: pd.Series | None = None
    by_symbol: pd.Series | None = None
    hourly: pd.Series | None = None
    errors: dict[str, str] = field(default_factory=dict)


def fetch_all(last_stamp: pd.Timestamp, run_date: pd.Timestamp, fetch=get) -> Fetched:
    """The four requests of a run. Never raises: a failure is recorded."""
    window_from = last_stamp - pd.Timedelta(days=4)
    since = int((window_from - pd.Timedelta(days=7)).tz_localize("UTC").timestamp())
    f = Fetched(front=symbol(*contract_on(run_date.date())))
    wanted = (("bz", chart_url("BZ=F", "1d", HISTORY_FROM), daily),
              ("fx_daily", chart_url("NZDUSD=X", "1d", HISTORY_FROM), daily),
              ("by_symbol", chart_url(f.front, "1d", since), daily),
              ("hourly", chart_url("NZDUSD=X", "60m", int(time.time()) - 2 * 86400),
               lambda s: s))
    for name, url, convert in wanted:
        try:
            s = convert(parse_chart(fetch(url)))
            if s.empty:
                raise ValueError("no bars")
            setattr(f, name, s)
        except Exception as e:                  # noqa: BLE001 — the guard decides
            f.errors[name] = f"{type(e).__name__}: {e}"
    return f


def assemble(f: Fetched, last_stamp: pd.Timestamp,
             run_date: pd.Timestamp) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """The run's Brent in USD, its FX, and the window's provenance."""
    usd, prov = window_usd(f.bz, f.by_symbol, last_stamp - pd.Timedelta(days=4), run_date)
    if f.hourly is not None:
        fx = with_run_day(f.fx_daily, float(f.hourly.iloc[-1]), run_date)
        run_fx = f"hourly, {f.hourly.index[-1]:%Y-%m-%d %H:%M} UTC"
    else:
        fx, run_fx = f.fx_daily.rename("nzdusd"), "daily bar (no hourly)"
    cpl = brent_nzd_cpl(usd, fx)
    days = pd.to_datetime(prov.date)
    prov["nzdusd"] = fx.reindex(days).to_numpy()
    prov["fx_source"] = np.where(days == run_date, run_fx, "daily bar")
    prov["cpl"] = cpl.reindex(days).to_numpy()
    return usd, fx, prov


# --- the guard -------------------------------------------------------------------
# It trips on a missing day, on a daily move no history has seen, and on a
# window day whose contract cannot be confirmed. Wednesday alone missing falls
# back to the two-day nowcast; anything else to plain `adl_ecm`. Measured on
# Yahoo's history, 9 Nov 2026:
#
#   Brent, within one contract, 2016-2026: the largest daily |log move| is
#   0.280 (21 Apr 2020), then 0.276 (9 Mar 2020); p99.9 is 0.163. Across a
#   roll it reaches 0.157, which is why the move is measured within one.
#   NZDUSD=X, 2005-2026: 0.068 (23 Oct 2008); p99.9 is 0.043.
#
# Both thresholds sit above the record. The guard is for bad data, not for a
# volatile week, and a threshold at p99.9 would switch the nowcast off on the
# crisis days where it is worth most.
#
# A missing day is told from a holiday by the two Brent series: a weekday
# neither BZ=F nor the contract by symbol has is a day the market was shut —
# 101 weekdays in 2016-2026, NYMEX's US holidays and a few one-offs — and the
# backtest's mean skipped it the same way. On the run day the two cannot tell a
# late bar from a holiday, and a Wednesday holiday can only be a fixed date.
# FX has no bar dated Friday under BST (336 Fridays in 2016-2026); the
# backtest drops those Fridays too, so they are not missing.
#
# Replayed over 557 Wednesday runs, 2016-2026, with BZ=F standing in for the
# contract by symbol (9 Nov 2026): 555 three days; one two days, 5 Dec 2018,
# a US day of mourning; one adl_ecm, 22 May 2019, where a gap in FX history
# fell on the last day before the run and cannot be told from a stale series.
# Six runs fell back before gaps were told from staleness at all.

MAX_MOVE_BRENT = 0.30
MAX_MOVE_FX = 0.08
FIXED_US_HOLIDAYS = {(1, 1), (6, 19), (7, 4), (12, 25)}
LONDON = ZoneInfo("Europe/London")
CONFIRM_CENTS = 0.005               # BZ=F equal to the next contract to the cent


@dataclass
class Decision:
    days: int                       # 3, 2, or 0: no nowcast, plain adl_ecm
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return {3: "three days", 2: "two days, Monday-Tuesday",
                0: "no nowcast, adl_ecm"}[self.days]


def _bst(day: pd.Timestamp) -> bool:
    return dt.datetime(day.year, day.month, day.day, 12, tzinfo=LONDON).utcoffset() > dt.timedelta(0)


def _closed(day: pd.Timestamp, f: Fetched, run_date: pd.Timestamp) -> bool:
    if day < run_date:
        return day not in f.bz.index and day not in f.by_symbol.index
    return (day.month, day.day) in FIXED_US_HOLIDAYS


def _big_moves(s: pd.Series, limit: float, same=lambda a, b: True) -> list[str]:
    out = []
    for (d0, p0), (d1, p1) in zip(s.items(), list(s.items())[1:]):
        m = abs(np.log(p1 / p0))
        if same(d0, d1) and m > limit:
            out.append(f"{d1:%a %d %b}: |log move| {m:.3f} from {d0:%d %b}, above {limit}")
    return out


def guard(f: Fetched, last_stamp: pd.Timestamp, run_date: pd.Timestamp,
          usd: pd.Series | None = None, fx: pd.Series | None = None,
          prov: pd.DataFrame | None = None) -> Decision:
    """Which nowcast this run may use, and why."""
    hard = {k: v for k, v in f.errors.items() if k != "hourly"}
    if hard:
        return Decision(0, [f"{k}: {v}" for k, v in hard.items()])
    notes = [f"hourly: {f.errors['hourly']}"] if "hourly" in f.errors else []
    if usd is None:
        usd, fx, prov = assemble(f, last_stamp, run_date)

    nxt = last_stamp + pd.Timedelta(days=7)
    wednesday = nxt - pd.Timedelta(days=2)
    required = list(pd.bdate_range(last_stamp - pd.Timedelta(days=4), last_stamp)) \
        + list(pd.bdate_range(nxt - pd.Timedelta(days=4), wednesday))
    open_days = [day for day in required if not _closed(day, f, run_date)]
    missing = [(day, "no Brent price") for day in open_days if day not in usd.index]
    reasons = []

    # FX. The run day has its own price, so only it can be missing. Before it,
    # a day without a bar in a series that runs past it is a gap in Yahoo's
    # history — four such in 2016-2026, still there today — and the backtest's
    # mean skipped it the same way, so it is noted, not tripped on. A series
    # that stops short of the last trading day before the run is stale.
    before = [day for day in open_days if day < run_date]
    if before and f.fx_daily.index.max() < before[-1]:
        reasons.append(f"FX daily ends {f.fx_daily.index.max():%a %d %b}, "
                       f"before {before[-1]:%a %d %b}: the series is stale")
    for day in open_days:
        if day in usd.index and day not in fx.index and not (day.dayofweek == 4 and _bst(day)):
            if day >= run_date:
                missing.append((day, "no FX"))
            else:
                notes.append(f"{day:%a %d %b}: no FX bar, skipped as the backtest skips it")

    lo = last_stamp - pd.Timedelta(days=11)
    reasons += _big_moves(usd[lo:run_date], MAX_MOVE_BRENT,
                          lambda a, b: contract_on(a.date()) == contract_on(b.date()))
    reasons += _big_moves(fx[lo:run_date], MAX_MOVE_FX)

    for r in prov[prov.usd_source == "BZ=F daily"].itertuples():
        day = pd.Timestamp(r.date)
        if day not in f.by_symbol.index:
            reasons.append(f"{day:%a %d %b}: {r.contract} from BZ=F cannot be checked "
                           f"against {f.front}, which has no bar that day")
        elif abs(r.usd - f.by_symbol[day]) < CONFIRM_CENTS:
            reasons.append(f"{day:%a %d %b}: BZ=F equals {f.front} ({r.usd:.2f}), so it "
                           f"still shows the next contract, not {r.contract}")

    said = [f"{d:%a %d %b}: {why}" for d, why in missing]
    if reasons or any(d != wednesday for d, _ in missing):
        return Decision(0, reasons + said, notes)
    if missing:
        return Decision(2, said, notes)
    return Decision(3, [], notes)


def main() -> int:
    run_date = pd.Timestamp(dt.datetime.now(dt.UTC).date())
    frames = {fuel: bt.load(fuel) for fuel in FUELS}
    last = max(d.index[-1] for d in frames.values())
    nxt = last + pd.Timedelta(days=7)
    print(f"Run day {run_date:%a %d %b %Y} UTC. Panel ends {last:%d %b %Y}; "
          f"the week in progress is stamped {nxt:%d %b %Y}.\n")

    f = fetch_all(last, run_date)
    prov, cpl = None, None
    if not {"bz", "fx_daily", "by_symbol"} & f.errors.keys():
        usd, fx, prov = assemble(f, last, run_date)
        cpl = brent_nzd_cpl(usd, fx)
        print(prov.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        decision = guard(f, last, run_date, usd, fx, prov)
    else:
        decision = guard(f, last, run_date)

    print(f"\nGuard: {decision.label}")
    for line in decision.reasons:
        print(f"  reason  {line}")
    for line in decision.notes:
        print(f"  note    {line}")

    if decision.days:
        k = decision.days
        print(f"\nEstimated d_cost for the week in progress, c/L, {k} days:")
        for fuel, d in frames.items():
            x = features(cpl, d.index.append(pd.DatetimeIndex([nxt])))[f"x{k}"].to_numpy()
            est = nowcast_at(x, d.d_cost.to_numpy(), d.is_final.to_numpy(), len(d) - 1)
            print(f"  {fuel:<19} feature {x[-1]:+7.3f}    estimate {est:+7.3f}")

    if prov is not None:
        WINDOW_CSV.parent.mkdir(exist_ok=True)
        prov.to_csv(WINDOW_CSV, index=False)
        print(f"\nwindow written to {WINDOW_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
