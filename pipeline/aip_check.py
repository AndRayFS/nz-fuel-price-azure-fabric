"""Independent check on the weekly MBIE ingest, using Australian data.

WHY THIS EXISTS. On 19 Aug 2026 the pipeline reloaded bronze from a
week-old CSV and reported success: two runs finished `Succeeded`, dbt ran
clean, all 60 tests passed, and Report 1 sat a week behind. Nothing below
the copy activity could tell. Every layer we own is downstream of the same
file, so no test we write can catch a stale-but-well-formed source.

This is the outside opinion. The Australian Institute of Petroleum
publishes a weekly PDF carrying the Argus Singapore product quote -- the
same Argus quote MBIE builds `Importer cost` from (Gasoil for diesel,
MOGAS95 for petrol) -- and publishes it on Sunday, three days before MBIE's
Wednesday release. If our newest week disagrees with theirs, something is
wrong with the ingest, not with the market.

WHAT IT VERIFIES, AND WHAT IT CANNOT. Verified empirically over 20 weeks
(Oct 2025 - Aug 2026): `Importer cost` tracks the AIP quote with a level
correlation of 0.9992 (diesel) and 0.9998 (petrol), and weekly changes at
0.997. The gap between them -- freight, wharfage, quality premium and the
mismatch between AIP's 10ppm marker and MBIE's 50ppm high-pour one -- is
NOT a constant: diesel's went 6.9 -> 13.4 USD/bbl over those months while
petrol's held at 7.4 - 9.6. So the check is on the WEEK-ON-WEEK MOVE, which
is stable, never on the level, which drifts.

Cause of that diesel drift is unresolved. Freight cannot be ruled out --
petrol and diesel move in segregated parcels on different vessels and the
route rate may differ by product -- so the candidates remain freight,
quality premium, and specification spread. Do not assert one of them.

SOURCE HAS NO ARCHIVE. AIP keeps only the most recent reports (15 diesel,
11 petrol when surveyed); older files are deleted, and Mar-Jun 2026 is
already gone. Hence `--append`: the CSV accumulates, so weeks survive here
after they vanish upstream. Each report carries TWO weeks, "Last Week" and
"Previous Week", so a missed run costs nothing.

Data is Argus, published by AIP under licence. Attribution required if any
of it is republished; see the notes page of any report.

WHAT THIS SCRIPT DOES, AND WHAT IT NO LONGER DOES. It fetches, parses,
converts and appends. It does not compare and it does not judge. The
comparison against `importer_cost` is `models/monitoring/monitor_aip_gap.sql`
and its warn-level tests, so it runs in the warehouse, over data everyone can
see, instead of against a CSV on one laptop. This script therefore always
exits 0: a discrepancy is a signal, and signals do not stop the weekly run.

The store it writes is the warehouse table `monitoring.aip_singapore_weekly`,
through `warehouse_write.append_new`. It used to be a seed CSV committed to
git and loaded by `dbt seed`; that route is gone (`seeds/monitoring/` with it),
because it made git the transport for data nobody writes by hand and made
every CI run a bot commit -- see `warehouse_write`'s own docstring.

That table is the only copy of the weeks AIP has already deleted, so it is
appended to and never regenerated. `append_new` inserts rows whose key is
missing and never revisits one already there, which is why `add_usd` refuses
to price a week on an FX window it cannot justify: a wrong rate would not be
corrected on the next run, it would simply stay.

Usage:
    python pipeline/aip_check.py            # fetch, parse, append to the table
    python pipeline/aip_check.py --no-fetch # re-parse the cached PDFs only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

import warehouse_write

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CACHE = REPO / "data" / ".aip_cache"
# The PDFs stay local and disposable; the extracted weeks are the asset, and
# they live in the seed that `monitoring` is built from.
SCHEMA = "monitoring"
TABLE = "aip_singapore_weekly"

# Types pinned here rather than inferred, for the reason the seed's yml gave:
# an empty input left dbt-fabric nothing to infer from and it made `fuel` an
# int, turning a warn-level test into a cast error.
DDL = f"""
create table {SCHEMA}.{TABLE} (
    week            date         not null,
    fuel            varchar(20)  not null,
    tapis_aucpl     float            null,
    brent_aucpl     float            null,
    product_aucpl   float            null,
    aud_usd         float            null,
    product_usd_bbl float            null,
    loaded_at       datetime2(3) not null
)
"""

API = "https://aip.com.au/wp-json/wp/v2/media"
LITRES_PER_BBL = 158.987
FX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSAL"
# A Mon-Fri week holds five business days, and US holidays remove at most two
# of them, never three -- so a window this short means the series is ragged
# there, not that the week was quiet.
MIN_FX_DAYS = 3

# The table sits on page 3 of every report seen so far, as
#   Average:  Last Week (to Friday 14/08/26)  88.5  83.2  142.5
# in the column order Tapis, North Sea Dated (Brent), product.
ROW = r"Average:\s*{label} Week \(to Friday ([\d/]+)\)\s*([\d.]+)\s*([\d.]+)\s*([\d.]+)"

REPORTS = {"Diesel": "Weekly-Diesel-Prices-Report", "Regular Petrol": "Weekly-Petrol-Prices-Report"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "nz-fuel-price-project ingest check"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_pdfs() -> None:
    """Download any report we do not already hold. Never deletes.

    Network failures are reported and stepped over: whatever is already in the
    cache still parses, and a week we could not reach today comes back in the
    next report, which carries two weeks.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    for fuel, slug in REPORTS.items():
        try:
            listing = json.loads(_get(f"{API}?search={slug}&per_page=100&_fields=source_url"))
        except Exception as exc:
            print(f"  ! {fuel}: could not reach the AIP media API: {exc}", file=sys.stderr)
            continue
        new = 0
        for item in listing:
            url = item["source_url"]
            dest = CACHE / url.rsplit("/", 1)[-1]
            if not dest.exists():
                try:
                    dest.write_bytes(_get(url))
                except Exception as exc:
                    print(f"  ! {fuel}: {url.rsplit('/', 1)[-1]} failed: {exc}", file=sys.stderr)
                    continue
                new += 1
        print(f"  {fuel}: {len(listing)} on server, {new} newly downloaded")


def parse() -> pd.DataFrame:
    """Both week rows out of every cached PDF, deduplicated by week."""
    from pypdf import PdfReader

    rows = []
    for fuel, slug in REPORTS.items():
        for pdf in sorted(CACHE.glob(f"{slug}*.pdf")):
            try:
                text = PdfReader(pdf).pages[2].extract_text()
            except Exception as exc:  # a re-styled PDF must fail loudly, not silently
                print(f"  ! could not read {pdf.name}: {exc}", file=sys.stderr)
                continue
            for label in ("Last", "Previous"):
                m = re.search(ROW.format(label=label), text)
                if not m:
                    continue
                rows.append(
                    {
                        "week": pd.to_datetime(m.group(1), format="%d/%m/%y"),
                        "fuel": fuel,
                        "tapis_aucpl": float(m.group(2)),
                        "brent_aucpl": float(m.group(3)),
                        "product_aucpl": float(m.group(4)),
                    }
                )
    if not rows:
        # Loud, but not fatal: a re-styled PDF is a problem with the check, not
        # with the data, and must not take the weekly recompute down with it.
        # The store simply stops advancing, which
        # `tests/monitoring/aip_latest_week_out_of_step.sql` then warns about.
        print("  ! no report tables parsed - the PDF layout has probably changed", file=sys.stderr)
        return pd.DataFrame(columns=["week", "fuel", "tapis_aucpl", "brent_aucpl", "product_aucpl"])
    return pd.DataFrame(rows).drop_duplicates(["week", "fuel"]).sort_values(["fuel", "week"])


def add_usd(df: pd.DataFrame) -> pd.DataFrame:
    """AU cents/litre -> USD/bbl, on the Mon-Fri mean rate of the stamped week.

    A week the FX series does not reach is DROPPED, loudly, never converted on
    whatever window happens to be available. Two reasons, and the second is the
    binding one:

    FRED's lag is not a constant. On 8 Sep 2026 DEXUSAL ended at 28 Aug; on
    10 Sep it ended at 4 Sep. So "the last five observations" and "the five
    days of this week" are the same window only some of the time, and when
    they are not, the older window is silently substituted -- and two report
    weeks sharing a frozen rate zero out the FX part of the week-on-week move,
    which is the only thing `monitor_aip_gap` compares.

    And `warehouse_write.append_new` inserts weeks it does not already hold and
    never revisits one. A rate computed from the wrong days is therefore not a
    transient error: it is written into the history permanently. Waiting costs
    nothing -- every report carries two weeks, so the next run picks the week
    up once the series has caught up.
    """
    raw = _get(FX_URL).decode()
    fx = pd.read_csv(pd.io.common.StringIO(raw), na_values=".")
    fx.columns = ["date", "usd_per_aud"]
    fx["date"] = pd.to_datetime(fx["date"])

    # Holidays are published as "." rows, so the frame BEFORE dropna is what
    # says how far the series reaches, and the one after is what can be
    # averaged. Reading coverage off the dropped frame would reject a week
    # whose Friday happened to be a US holiday.
    covered_to = fx["date"].max()
    rates = fx.dropna().set_index("date")["usd_per_aud"].sort_index()

    rate: dict[pd.Timestamp, float] = {}
    for week in pd.to_datetime(df["week"].unique()):
        if week > covered_to:
            print(f"  ! FX series stops at {covered_to.date()}, so the week to "
                  f"{week.date()} is not covered; left for a later run",
                  file=sys.stderr)
            continue
        # The stamp is the Friday, so Mon-Fri is [w-4, w] -- stated as dates
        # rather than as a count of rows, which is what let an older window in.
        window = rates.loc[week - pd.Timedelta(days=4):week]
        if len(window) < MIN_FX_DAYS:
            print(f"  ! only {len(window)} FX observation(s) in the week to "
                  f"{week.date()}; left for a later run", file=sys.stderr)
            continue
        rate[week] = window.mean()

    if not rate:
        raise RuntimeError(
            f"the FX series covers none of the {df['week'].nunique()} parsed "
            f"weeks; it stops at {covered_to.date()}"
        )

    print(f"  FX series reaches {covered_to.date()}; priced {len(rate)} of "
          f"{df['week'].nunique()} weeks")
    kept = df[df["week"].isin(list(rate))].copy()
    kept["aud_usd"] = kept["week"].map(rate)
    kept["product_usd_bbl"] = kept["product_aucpl"] / 100 * kept["aud_usd"] * LITRES_PER_BBL
    return kept




def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-fetch", action="store_true", help="use cached PDFs only")
    args = ap.parse_args()

    if not args.no_fetch:
        print("Fetching report list from the AIP media API...")
        fetch_pdfs()

    parsed = parse()
    if parsed.empty:
        print("Nothing parsed; the stored weeks are left exactly as they were.")
        return 0

    try:
        priced = add_usd(parsed)
    except Exception as exc:
        # No FRED, no conversion, and half-converted rows are worse than none.
        # Covers both shapes: the fetch failing, and the series not reaching a
        # single one of the parsed weeks.
        print(f"! no FX conversion ({exc}); store left unchanged", file=sys.stderr)
        return 0

    priced = priced.drop_duplicates(["week", "fuel"], keep="last")
    priced["loaded_at"] = pd.Timestamp.now('UTC').tz_localize(None)

    # append_new, never replace: this table IS the history. AIP keeps 11-15
    # reports on its site and Mar-Jun 2026 is already gone from it, so a
    # truncate here loses weeks that cannot be fetched again from anywhere.
    warehouse_write.append_new(
        priced[["week", "fuel", "tapis_aucpl", "brent_aucpl", "product_aucpl",
                "aud_usd", "product_usd_bbl", "loaded_at"]],
        SCHEMA, TABLE, DDL, key=["week", "fuel"],
    )

    counts = priced.groupby("fuel")["week"].agg(["count", "min", "max"])
    print(f"\nParsed {len(priced)} rows from the cached reports:")
    for fuel, r in counts.iterrows():
        print(f"  {fuel:15s} {r['count']:3d} weeks  {r['min'].date()} .. {r['max'].date()}")

    print("\nRead the signals:")
    print("  dbt build --select monitor_aip_gap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
