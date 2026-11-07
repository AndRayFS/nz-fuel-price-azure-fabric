"""Probe Yahoo's chart endpoint from wherever this runs — W23, step 1, 7 Nov 2026.

The nowcast (docs/workstreams.md, W23) would put an undocumented Yahoo endpoint
inside the weekly chain. Before any of it is built, three questions have to be
answered from a GitHub runner rather than from the laptop:

  1. Does Yahoo answer a runner at all? The first dispatch says.
  2. Is a live daily bar the settlement? Daily closes in Yahoo's history are
     settlements (docs/research.md, "Yahoo's Brent rolls twice"); the bar a
     request sees on the day itself has not been measured.
  3. When does Yahoo rewrite past BZ=F days around BZF27's expiry on
     30 Nov 2026? Its live view moves to the next contract 4-9 trading days
     early, and the daily history is rewritten later (18 Sep: 98.77 on the
     19th, 103.87 since).

So it interprets nothing. Every answer is saved as Yahoo sent it, beside a
manifest of what was asked, when, how long it took and what came back. Reading
them is later work, done on the artifacts.

One run, eight requests a second apart:

  BZ=F          daily, 14 calendar days (about 10 trading days); hourly, 2 days
  front, next   the calendar front and next contracts by symbol (BZF27.NYM and
                BZG27.NYM on 7 Nov 2026): daily, 14 days; 15-minute, 2 days
  previous      the contract that expired last, daily. Expired symbols have
                answered 404, which is one of the guard's trip conditions.
  NZDUSD=X      hourly, 2 days

The request is the one research/nowcast_brent.py makes — same host, path and
User-Agent, only `period1` and `interval` differ — so "the runner is answered"
means the research request is answered. No retries: a retry would hide exactly
what this measures.

Run by .github/workflows/probe-yahoo.yml, and as a non-blocking first step of
weekly.yml. Standard library only, so it runs before anything is installed.

Exits 1 only if no request came back 200, which is question 1 answered "no".
The expired contract's 404 is expected and is not a failure.

Usage:  python pipeline/probe_yahoo.py [--out DIR]
Writes  DIR/<UTC stamp>/: manifest.csv, run.json and one JSON file per request.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[1]

URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
       "?period1={p1}&period2=9999999999&interval={interval}")
HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 15        # seconds per request: eight of them fit the step's 3 minutes
PAUSE = 1.0         # seconds between requests
MONTH_CODE = "FGHJKMNQUVXZ"


# The expiry calendar. ICE Brent, which NYMEX BZ follows, from the March 2016
# contract: the last London business day of the second month before the
# contract month. The rule is research/roll_weeks.new_rule, restated without
# pandas; the two agree on every contract from March 2016 to April 2027
# (checked 7 Nov 2026). As there, only the holidays that can end a month count.

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


def calendar_contracts(today: dt.date) -> dict[str, tuple[str, dt.date]]:
    """Previous, front and next contracts on `today`: symbol and expiry.

    The front is the first contract whose expiry is today or later — on its
    last trading day a contract still trades, and settles, as the front.
    """
    y, m = today.year, today.month
    while expiry(y, m) < today:
        y, m = _step(y, m, 1)
    out = {}
    for role, k in (("previous", -1), ("front", 0), ("next", 1)):
        cy, cm = _step(y, m, k)
        out[role] = (f"BZ{MONTH_CODE[cm - 1]}{cy % 100:02d}.NYM", expiry(cy, cm))
    return out


def plan(today: dt.date) -> tuple[list[tuple[str, str, str, int]], dict]:
    """The requests, as (role, symbol, interval, days back)."""
    c = calendar_contracts(today)
    return [
        ("continuous", "BZ=F", "1d", 14),
        ("continuous", "BZ=F", "60m", 2),
        ("previous", c["previous"][0], "1d", 14),
        ("front", c["front"][0], "1d", 14),
        ("front", c["front"][0], "15m", 2),
        ("next", c["next"][0], "1d", 14),
        ("next", c["next"][0], "15m", 2),
        ("fx", "NZDUSD=X", "60m", 2),
    ], c


def fetch(url: str) -> tuple[int | None, bytes, int, str, str]:
    """(HTTP status, body, latency in ms, final URL, error). Never raises."""
    req = urllib.request.Request(url, headers=HEADERS)
    status, body, final, error = None, b"", "", ""
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            status, final, body = r.status, r.geturl(), r.read()
    except urllib.error.HTTPError as e:
        status, final, error = e.code, e.geturl() or "", str(e)
        try:
            body = e.read()
        except Exception:                       # noqa: BLE001 — keep the status
            pass
    except Exception as e:                      # noqa: BLE001 — a probe records
        error = f"{type(e).__name__}: {e}"
    return status, body, round((time.monotonic() - t0) * 1000), final, error


def _utc(ts) -> str:
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d %H:%M") if ts else ""


def summarise(body: bytes) -> dict:
    """What a reader wants at a glance. Best effort; the raw file is the record."""
    try:
        chart = json.loads(body)["chart"]
    except Exception:                           # noqa: BLE001
        return {}
    if chart.get("error"):
        return {"yahoo_error": chart["error"].get("description", "")}
    try:
        res = chart["result"][0]
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0].get("close") or []
        meta = res.get("meta", {})
    except Exception:                           # noqa: BLE001
        return {}
    last = next(((t, c) for t, c in zip(reversed(ts), reversed(closes))
                 if c is not None), (None, None))
    return {"bars": len(ts), "last_bar_utc": _utc(last[0]), "last_close": last[1],
            "market_price": meta.get("regularMarketPrice"),
            "market_time_utc": _utc(meta.get("regularMarketTime"))}


COLUMNS = ["role", "symbol", "interval", "days", "fetched_at_utc", "http_status",
           "latency_ms", "bytes", "error", "yahoo_error", "bars", "last_bar_utc",
           "last_close", "market_price", "market_time_utc", "file", "url", "final_url"]


def _g(x) -> str:
    return f"{x:g}" if isinstance(x, float) else str(x)


def report(rows: list[dict], contracts: dict, started: dt.datetime) -> str:
    """The step summary. Prices are rounded here only; the manifest keeps Yahoo's."""
    ok = sum(r["http_status"] == 200 for r in rows)
    lines = [f"### Yahoo probe, {started:%Y-%m-%d %H:%M:%S} UTC — {ok} of {len(rows)} answered 200",
             "",
             "Calendar: " + ", ".join(f"{role} `{s}` (expires {e:%d %b %Y})"
                                      for role, (s, e) in contracts.items()),
             "",
             "| request | HTTP | ms | bars | last bar, UTC | last close | live price | live time, UTC |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        status = r["http_status"] or r["error"] or "none"
        if r["yahoo_error"]:
            status = f"{status}: {r['yahoo_error']}"
        lines.append(f"| `{r['symbol']}` {r['interval']} | {status} | {r['latency_ms']} "
                     f"| {r['bars']} | {r['last_bar_utc']} | {_g(r['last_close'])} "
                     f"| {_g(r['market_price'])} | {r['market_time_utc']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Record Yahoo's raw answers for W23.")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "probe_yahoo",
                    help="parent directory; each run writes a UTC-stamped folder in it")
    args = ap.parse_args()

    started = dt.datetime.now(dt.UTC)
    out = args.out / started.strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    requests, contracts = plan(started.date())

    rows = []
    for i, (role, sym, interval, days) in enumerate(requests):
        if i:
            time.sleep(PAUSE)
        fetched = dt.datetime.now(dt.UTC)
        p1 = int((fetched - dt.timedelta(days=days)).timestamp())
        url = URL.format(sym=sym, p1=p1, interval=interval)
        status, body, ms, final, error = fetch(url)
        name = f"{role}_{interval}.json"
        if body:
            (out / name).write_bytes(body)
        row = dict.fromkeys(COLUMNS, "")
        row.update(role=role, symbol=sym, interval=interval, days=days,
                   fetched_at_utc=fetched.isoformat(timespec="seconds"),
                   http_status=status, latency_ms=ms, bytes=len(body), error=error,
                   file=name if body else "", url=url,
                   final_url=final if final != url else "")
        row.update(summarise(body))
        rows.append(row)

    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    (out / "run.json").write_text(json.dumps({
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "contracts": {k: {"symbol": s, "expiry": e.isoformat()}
                      for k, (s, e) in contracts.items()},
        "github": {k: os.environ.get(k, "") for k in
                   ("GITHUB_WORKFLOW", "GITHUB_EVENT_NAME", "GITHUB_RUN_ID",
                    "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "RUNNER_NAME")},
        "python": platform.python_version(),
    }, indent=2) + "\n")

    text = report(rows, contracts, started)
    print(text)
    print(f"written to {out}")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(text)
    return 0 if any(r["http_status"] == 200 for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
