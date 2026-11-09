"""NYMEX BZ volume by contract and by week, 31 Aug - 5 Nov 2026. 10 Nov 2026.

Descriptive, no rule: where the trading is along the curve, how it moves at an
expiry, and whether the day the next contract out-trades the front matches the
day Yahoo's live BZ=F view switches (23 Oct 2026, docs/research.md, 7 Nov).

Each contract live on 10 Nov 2026 is read by its own symbol. The two that
expired inside the window, BZX26 (30 Sep) and BZZ26 (30 Oct), answer 404, so
their volume is BZ=F's while each was the calendar front; their days as second
month are lost, and September's totals are lower bounds. Left out:
  - 6 Nov 2026, on which every contract's volume is 5 Nov's to the unit, still
    so on 9 Nov;
  - BZ=F on an expiry day, which carries the next contract's volume (30 Oct:
    BZF27's to the unit).
One contract is 1,000 bbl (NYMEX rulebook, chapter 698); notional is
contracts x 1,000 x the day's close. NYMEX only: ICE, where most Brent trades,
is not on Yahoo.

`--save DIR` keeps the raw answers, `--raw DIR` reads them back; the 10 Nov
answers are in `data/roll_volumes/`.

    python research/roll_volumes.py [--save DIR | --raw DIR]
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import nowcast as nc                          # noqa: E402

FROM, TO = pd.Timestamp("2026-08-31"), pd.Timestamp("2026-11-05")
MONTH = "FGHJKMNQUVXZ"
SYMBOLS = ["BZ=F"] + [f"BZ{c}27.NYM" for c in MONTH] + ["BZZ28.NYM", "BZZ29.NYM"]
EXPIRY = {pd.Period("2026-11", "M"): pd.Timestamp("2026-09-30"),
          pd.Period("2026-12", "M"): pd.Timestamp("2026-10-30"),
          pd.Period("2027-01", "M"): pd.Timestamp("2026-11-30")}
COPIED = pd.Timestamp("2026-11-06")


def fetch(save: Path | None) -> dict[str, bytes]:
    p1, now = calendar.timegm(dt.date(2026, 8, 20).timetuple()), int(time.time())
    out = {}
    for s in SYMBOLS:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={now}&interval=1d"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=nc.HEADERS),
                                        timeout=nc.TIMEOUT) as r:
                out[s] = r.read()
        except urllib.error.HTTPError as e:
            print(f"{s}: HTTP {e.code}")
            continue
        if save:
            save.mkdir(parents=True, exist_ok=True)
            (save / f"{s}.json").write_bytes(out[s])
        time.sleep(1)
    return out


def bars(body: bytes) -> pd.DataFrame:
    r = json.loads(body)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    idx = (pd.to_datetime(r["timestamp"], unit="s", utc=True)
           .tz_convert("America/New_York").tz_localize(None).normalize())
    return pd.DataFrame({"close": q["close"], "volume": q["volume"]}, index=idx).dropna()


def front(d: pd.Timestamp) -> pd.Period:
    return next(c for c, e in sorted(EXPIRY.items()) if d <= e)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--save", type=Path)
    g.add_argument("--raw", type=Path)
    args = ap.parse_args()
    raw = ({s: (args.raw / f"{s}.json").read_bytes() for s in SYMBOLS
            if (args.raw / f"{s}.json").exists()} if args.raw else fetch(args.save))

    rows = []
    for d, r in bars(raw["BZ=F"]).iterrows():         # the two expired fronts
        if d > EXPIRY[pd.Period("2026-12", "M")] or d in EXPIRY.values():
            continue
        rows.append(dict(date=d, contract=front(d), close=r.close, volume=r.volume, src="BZ=F"))
    for s in SYMBOLS[1:]:
        if s not in raw:
            continue
        c = pd.Period(f"20{s[3:5]}-{MONTH.index(s[2]) + 1:02d}", "M")
        for d, r in bars(raw[s]).iterrows():
            rows.append(dict(date=d, contract=c, close=r.close, volume=r.volume, src=s))
    v = pd.DataFrame(rows)
    v = v[(v.date >= FROM) & (v.date <= TO) & (v.date != COPIED)]
    v["mbbl"] = v.volume / 1000
    v["usd_bn"] = v.volume * 1000 * v.close / 1e9
    v["rank"] = [(c - front(d)).n + 1 for c, d in zip(v.contract, v.date)]

    print(f"== By contract, {FROM.date()} - {TO.date()} ==")
    t = v.groupby("contract").agg(days=("date", "nunique"), mbbl=("mbbl", "sum"),
                                  usd_bn=("usd_bn", "sum"), src=("src", "first"))
    t["share %"] = t.mbbl / t.mbbl.sum() * 100
    print(t.round(1).to_string())

    print("\n== By week, million bbl, by calendar rank (1 = front) ==")
    v["week"] = v.date - pd.to_timedelta(v.date.dt.weekday, unit="D")
    v["bucket"] = v["rank"].clip(upper=4).map({1: "front", 2: "2nd", 3: "3rd", 4: "4th+"})
    w = v.pivot_table(index="week", columns="bucket", values="mbbl", aggfunc="sum").fillna(0)
    w = w[["front", "2nd", "3rd", "4th+"]]
    w["total"] = w.sum(axis=1)
    w["usd bn"] = v.groupby("week").usd_bn.sum()
    w["front %"] = w.front / w.total * 100
    w["front is"] = v[v["rank"] == 1].groupby("week").contract.agg(
        lambda s: " > ".join(sorted({str(x) for x in s})))
    print(w.round(0).to_string())

    print("\n== Daily, thousand contracts: the October roll ==")
    a = v[(v.date >= "2026-10-15") & (v.date <= "2026-11-03")
          & v.contract.isin([pd.Period(m, "M") for m in ("2026-12", "2027-01", "2027-02")])]
    print((a.pivot_table(index="date", columns="contract", values="volume", aggfunc="sum") / 1000)
          .round(1).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
