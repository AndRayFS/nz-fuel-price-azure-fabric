"""Publish what Report 1 is built from, as one dated archive per load.

Report 1 is public through publish-to-web, and publish-to-web cannot export
data from visuals, so a reader who wants the numbers needs another way to get
them. This writes three CSVs and a README into one zip and puts it in Azure
Blob Storage, under a public container:

    https://nzfueldata.blob.core.windows.net/data/<YYYY-MM-DD>/nz-fuel-<YYYY-MM-DD>.zip
    https://nzfueldata.blob.core.windows.net/data/latest/nz-fuel-latest.zip

The dated archive is never rewritten by a later load. That is the point of
it: the file for a date is what the report showed after that load, readable
without a vintage run or a restore. Two loads on the same New Zealand date —
a rerun — write the same name, and the second wins.

The date is the LOAD's, not the data's. A week MBIE only revised
(`revised_in_place` in the gate) loads with no new week in it, and still
deserves its own archive.

Upload is one REST call per blob with an Entra token, not the storage SDK: the
same DefaultAzureCredential the rest of `pipeline/` uses, and no new
dependency. The identity needs Storage Blob Data Contributor on the `data`
container — `nz-fuel-ci` holds it since 16 Oct 2026.

Usage:  python pipeline/publish_data.py [--no-upload]

`--no-upload` builds the archive into data/publish/ and stops, for looking at
it. Exit codes: 0 published, 1 failed.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from azure.identity import DefaultAzureCredential

from fabric_io import connect

ACCOUNT_URL = "https://nzfueldata.blob.core.windows.net"
CONTAINER = "data"
STORAGE_SCOPE = "https://storage.azure.com/.default"
API_VERSION = "2023-11-03"

OUT = Path(__file__).parents[1] / "data" / "publish"

# One row per (week, fuel). MBIE's own weekly series, crude and exchange rate
# riding along from silver_general the way export_panel.py joins them.
WEEKLY_PRICES = """
select
    cast(f.Date as date)          as week_date,
    f.Week                        as mbie_week,
    f.Fuel                        as fuel,
    f.adjusted_retail_price,
    f.board_price,
    f.price_excl_tax,
    f.taxes,
    f.gst,
    f.ets,
    f.importer_cost,
    f.importer_margin,
    g.dubai_crude_usd,
    g.dubai_crude_nzd,
    g.exchange_rate,
    f.adjusted_retail_price_status,
    f.board_price_status,
    f.price_excl_tax_status,
    f.taxes_status,
    f.gst_status,
    f.ets_status,
    f.importer_cost_status,
    f.importer_margin_status,
    g.dubai_crude_usd_status,
    g.exchange_rate_status
from dbo.silver_fuel f
join dbo.silver_general g
    on g.Date = f.Date
order by f.Fuel, cast(f.Date as date)
"""

TABLES = {
    "weekly_prices.csv": WEEKLY_PRICES,
    "forecasts.csv": "select * from dbo.forecast_accuracy "
                     "order by fuel, horizon_weeks, week_date",
    "margin.csv": "select * from dbo.margin_compression order by fuel, week_date",
}

README = """\
NZ fuel prices: the weekly data behind Report 1
================================================

Published {published} (New Zealand time). MBIE data through the week of
{through}.

Project: https://github.com/AndRayFS/nz-fuel-price-azure-fabric

Source: Ministry of Business, Innovation and Employment (MBIE), Weekly fuel
price monitoring, licensed under Creative Commons Attribution 4.0 (CC BY 4.0).
  Data:        https://www.mbie.govt.nz/assets/Data-Files/Energy/Weekly-fuel-price-monitoring/weekly-table.csv
  Methodology: https://www.mbie.govt.nz/dmsdocument/30707-weekly-fuel-price-monitoring-methodology
Everything in forecasts.csv and in the derived columns of margin.csv is this
project's own calculation on MBIE's data, not MBIE's.

Each archive is the data as it stood on its publication date, and is never
changed afterwards. MBIE revises published weeks, so two archives can
disagree about the same week; both are correct for their date.


weekly_prices.csv ({n_weekly_prices} rows)
  MBIE's weekly series, one row per week and fuel (Regular Petrol, Premium
  Petrol 95R, Diesel), from 2004. Prices and their components in NZ cents per
  litre; Dubai crude in USD and NZD per barrel; the exchange rate as MBIE
  publishes it. Every value has a status column: Provisional values can still
  change, Final ones normally do not.

forecasts.csv ({n_forecasts} rows)
  What Report 1 plots. For each week, fuel and horizon (1 to 3 weeks ahead):
  the pump price at the time (price_now), the price that followed
  (actual_price), the model's call (pred_adl_ecm, a distributed-lag model with
  error correction, on importer cost), the benchmark that the price does not
  move (pred_naive), their absolute errors, and the trailing 26-week accuracy
  (mae_*_26w, skill_26w: above zero means the model beat the benchmark).
  pred_adl is the same model without error correction; the report does not
  plot it.
  This is a walk-forward backtest: every row is refitted on data available at
  that week only - but on today's revised data. It is a retrospective
  simulation, not a record of what was published at the time. The crude_*
  columns describe what crude was doing when the call was made.

margin.csv ({n_margin} rows)
  How far each fuel's importer margin sits from its own recent normal, from
  29 Mar 2024. margin_norm_104w is the mean of the 104 weeks before the week;
  margin_gap_pct is the distance from it as a share of it. Gaps below -100%
  are real: the margin itself went negative in 2026.
  Read with these caveats:
  - The importer margin is a residual: MBIE's board price minus taxes,
    levies and an estimate of the cost of replacing the fuel at this week's
    prices. A sharp rise in cost compresses it mechanically.
  - From 27 Feb 2026 MBIE counts a "fuel market adjustment" in importer cost
    and takes it out of the margin (made on 23 Sep 2026 and applied
    backwards). For 27 Feb - 11 Sep 2026 this file separates it:
    adjustment_cpl, margin_before_adjustment and gap_before_adjustment_pct.
    Later weeks arrived already adjusted and cannot be separated.
  - cost_backfilled marks weeks for which MBIE suspended importer cost and
    margin (18 Mar - 1 Jul 2026) and filled them in later.
"""


def nz_today() -> str:
    return datetime.now(ZoneInfo("Pacific/Auckland")).date().isoformat()


def read_tables() -> dict[str, tuple[list[str], list[tuple]]]:
    out = {}
    with connect() as conn:
        cur = conn.cursor()
        for name, sql in TABLES.items():
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            out[name] = (cols, [tuple(r) for r in cur.fetchall()])
    return out


def to_csv(cols: list[str], rows: list[tuple]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build_archive(published: str) -> tuple[bytes, dict[str, int]]:
    tables = read_tables()
    counts = {name: len(rows) for name, (_, rows) in tables.items()}
    if not all(counts.values()):
        raise RuntimeError(f"an empty table would publish an empty file: {counts}")

    cols, rows = tables["weekly_prices.csv"]
    through = max(r[cols.index("week_date")] for r in rows)
    readme = README.format(
        published=published,
        through=through,
        n_weekly_prices=counts["weekly_prices.csv"],
        n_forecasts=counts["forecasts.csv"],
        n_margin=counts["margin.csv"],
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", readme)
        for name, (cols, rows) in tables.items():
            z.writestr(name, to_csv(cols, rows))
    return buf.getvalue(), counts


def upload(blob: str, body: bytes, cache_control: str | None = None) -> str:
    token = DefaultAzureCredential().get_token(STORAGE_SCOPE).token
    url = f"{ACCOUNT_URL}/{CONTAINER}/{blob}"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-ms-version": API_VERSION,
        "x-ms-blob-type": "BlockBlob",
        "x-ms-blob-content-type": "application/zip",
        "Content-Type": "application/zip",
    }
    if cache_control:
        headers["x-ms-blob-cache-control"] = cache_control
    req = urllib.request.Request(url, method="PUT", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status != 201:
                raise RuntimeError(f"upload of {blob} answered {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"upload of {blob} failed, {exc.code}: {detail}") from exc
    return url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-upload", action="store_true",
                    help="build into data/publish/ and stop")
    args = ap.parse_args()

    published = nz_today()
    archive, counts = build_archive(published)
    name = f"nz-fuel-{published}.zip"
    print(f"{name}: {len(archive):,} bytes, {counts}", file=sys.stderr)

    if args.no_upload:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(archive)
        print(f"written to {OUT / name}, not uploaded", file=sys.stderr)
        return 0

    # Dated first: if the second call fails, the record is complete and only
    # the convenience link is stale, which the next load repairs.
    print(upload(f"{published}/{name}", archive), file=sys.stderr)
    print(upload("latest/nz-fuel-latest.zip", archive, cache_control="no-cache"),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
