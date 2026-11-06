"""The phone landing page: one static HTML file, rebuilt from each archive.

Report 1 is a 1280-px desktop page, and publish-to-web does not serve Power
BI's mobile layout, so on a phone it arrives scaled to about 30%. This page is
what a phone reader gets instead - the newest week's price, the model's calls
for the next three, the margin, and how far the model has been off lately - at

    https://nzfueldata.z8.web.core.windows.net/

the storage account's static website: the `$web` container, with index.html
as its root. `publish_data.py` builds it from the same three tables it zips,
in the same run, so the page and the archive of a date never describe two
different loads, and nothing here reads the warehouse a second time.

Every figure follows Report 1's Now page, where the definitions live
(pbip/build/model_v2.py): the 4-week change on adjusted_retail_price; the
calls are pred_adl_ecm made in the newest week; their band is the middle half
of past misses (actual minus call) at that horizon, in weeks of the newest
week's crude-volatility regime, the three fuels pooled, outcomes known by the
newest week; the margin against its 104-week norm on a 0-60 c/L track, orange
whenever it is below. One block is the page's own: the misses, which set the
mean 1-week-ahead miss of the last four weeks against the fuel's mean over
the whole backtest (from 2013) - LARGER times it or more reads "Larger than
usual", SMALLER times it or less "Smaller than usual".

The page is pipeline/phone/template.html with the data dropped in as JSON.
Its QR code, pipeline/phone/qr.svg, encodes the address above; it was made
once with segno 1.6.6 (version 4, error correction Q, 33 modules) and changes
only if the address does, so the weekly run does not need segno.

Usage:  python pipeline/phone_page.py [ZIP | DIR]

builds data/publish/index.html from an archive - a local zip, a directory of
its CSVs, or by default the public latest one - with no warehouse and no
capacity: the way to look at a change to the page before a weekly run
publishes it.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent / "phone"
OUT = Path(__file__).parents[1] / "data" / "publish"
LATEST_ZIP = "https://nzfueldata.blob.core.windows.net/data/latest/nz-fuel-latest.zip"
CSVS = ("weekly_prices.csv", "forecasts.csv", "margin.csv")

# The switch's order, 91 / 95 / Diesel, with the colour under the chosen one.
FUELS = (("Regular Petrol", "#40B54A"), ("Premium Petrol 95R", "#E5C700"), ("Diesel", "#4D4C48"))
WEEKS = 13            # paid weeks on the chart, the newest included
RECENT = 4            # the newest misses, set against the usual one
LARGER, SMALLER = 1.5, 2 / 3


def _r(x, digits: int = 1):
    return None if x is None or pd.isna(x) else round(float(x), digits)


def compute(csvs: dict[str, bytes]) -> dict:
    """The page's data from the archive's three CSVs."""
    p = pd.read_csv(io.BytesIO(csvs["weekly_prices.csv"]), parse_dates=["week_date"])
    f = pd.read_csv(io.BytesIO(csvs["forecasts.csv"]), parse_dates=["week_date", "target_week"])
    m = pd.read_csv(io.BytesIO(csvs["margin.csv"]), parse_dates=["week_date"])
    if f.outcome_known.dtype != bool:
        raise RuntimeError(f"forecasts.csv outcome_known reads as {f.outcome_known.dtype}, not bool")

    latest = p.week_date.max()
    if f.week_date.max() != latest:
        raise RuntimeError(f"prices run to {latest.date()}, the calls to {f.week_date.max().date()}")
    weeks = [latest - pd.Timedelta(weeks=k) for k in range(WEEKS - 1, -1, -1)]
    now = f[f.week_date == latest]
    targets = sorted(now.target_week.unique())
    if len(targets) != 3:
        raise RuntimeError(f"expected calls for 3 weeks after {latest.date()}, found {len(targets)}")
    regime = now.crude_vol_regime.max()
    known = f[f.outcome_known & (f.target_week <= latest)]

    band = {}
    for h in (1, 2, 3):
        e = known[(known.crude_vol_regime == regime) & (known.horizon_weeks == h)]
        e = (e.actual_price - e.pred_adl_ecm).dropna()
        if e.empty:
            raise RuntimeError(f"no past misses at horizon {h} in the {regime!r} regime")
        band[h] = (e.quantile(0.25), e.quantile(0.75))

    fuels = []
    for name, colour in FUELS:
        paid = p[p.fuel == name].set_index("week_date").adjusted_retail_price
        price, then = paid.get(latest), paid.get(weeks[-5])
        if price is None or pd.isna(price):
            raise RuntimeError(f"no price for {name} in the week of {latest.date()}")
        has_then = then is not None and not pd.isna(then)

        calls = []
        for h in (1, 2, 3):
            c = now[(now.fuel == name) & (now.horizon_weeks == h)].pred_adl_ecm
            if len(c) != 1 or pd.isna(c.iloc[0]):
                raise RuntimeError(f"no single call for {name} at horizon {h} from {latest.date()}")
            c = float(c.iloc[0])
            calls.append([_r(c + band[h][0]), _r(c, 2), _r(c + band[h][1])])

        mg = m[(m.fuel == name) & (m.week_date == latest)]
        margin = norm = gap = None
        if len(mg) == 1:
            margin, norm = _r(mg.importer_margin.iloc[0]), _r(mg.margin_norm_104w.iloc[0])
            gap = _r(mg.importer_margin.iloc[0] - mg.margin_norm_104w.iloc[0])

        one = known[(known.fuel == name) & (known.horizon_weeks == 1)].set_index("target_week").abs_err_adl_ecm
        recent = one.reindex(weeks[-RECENT:]).dropna()
        if len(recent) < RECENT:
            raise RuntimeError(f"{name}: {len(recent)} of the last {RECENT} weeks have a known 1-week miss")
        m4, usual = recent.mean(), one.mean()
        ratio = m4 / usual
        verdict = ("Larger than usual" if ratio >= LARGER else
                   "Smaller than usual" if ratio <= SMALLER else "As usual")

        fuels.append(dict(
            color=colour,
            price=_r(price),
            chg=_r(price - then) if has_then else None,
            pct=_r(100 * (price - then) / then) if has_then else None,
            series=[_r(paid.get(w)) for w in weeks],
            calls=calls,
            margin=margin, norm=norm, gap=gap,
            miss=[_r(one.get(w)) for w in weeks],
            m4=_r(m4, 2), usual=_r(usual, 2), verdict=verdict,
        ))

    return dict(
        latest=latest.date().isoformat(),
        weeks=[w.date().isoformat() for w in weeks],
        targets=[pd.Timestamp(t).date().isoformat() for t in targets],
        recent=RECENT,
        regime=regime,
        fuels=fuels,
    )


def render(data: dict) -> str:
    page = (HERE / "template.html").read_text(encoding="utf-8")
    for mark in ("__DATA__", "<!--QR-->"):
        if page.count(mark) != 1:
            raise RuntimeError(f"template.html must hold {mark} exactly once")
    qr = (HERE / "qr.svg").read_text(encoding="utf-8").strip()
    blob = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    return page.replace("<!--QR-->", qr).replace("__DATA__", blob)


def read_archive(source: str | None) -> dict[str, bytes]:
    if source and Path(source).is_dir():
        return {n: (Path(source) / n).read_bytes() for n in CSVS}
    if source and not source.startswith("https://"):
        body = Path(source).read_bytes()
    else:
        with urllib.request.urlopen(source or LATEST_ZIP, timeout=60) as resp:
            body = resp.read()
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        return {n: z.read(n) for n in CSVS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", nargs="?", help="zip or directory of CSVs; default the public latest zip")
    args = ap.parse_args()
    data = compute(read_archive(args.archive))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render(data), encoding="utf-8")
    for (name, _), fu in zip(FUELS, data["fuels"]):
        print(f"{name}: {fu['price']} on {data['latest']}, calls "
              f"{[round(c[1]) for c in fu['calls']]}, margin gap {fu['gap']}, "
              f"misses {fu['m4']} vs {fu['usual']} - {fu['verdict']}", file=sys.stderr)
    print(f"written to {OUT / 'index.html'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
