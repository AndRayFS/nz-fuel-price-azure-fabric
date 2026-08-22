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

The store it writes is `seeds/monitoring/aip_singapore_weekly.csv`, which is
loaded with `dbt seed`. That file is the only copy of the weeks AIP has
already deleted -- append to it, never regenerate it.

Usage:
    python research/aip_check.py            # fetch, parse, append to the seed
    python research/aip_check.py --no-fetch # re-parse the cached PDFs only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CACHE = ROOT / "data" / ".aip_cache"
# The PDFs stay local and disposable; the extracted weeks are the asset, and
# they live in the seed that `monitoring` is built from.
OUT = REPO / "seeds" / "monitoring" / "aip_singapore_weekly.csv"

API = "https://aip.com.au/wp-json/wp/v2/media"
LITRES_PER_BBL = 158.987
FX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXUSAL"

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
    """AU cents/litre -> USD/bbl, on the Mon-Fri mean rate of the stamped week."""
    raw = _get(FX_URL).decode()
    fx = pd.read_csv(pd.io.common.StringIO(raw), na_values=".")
    fx.columns = ["date", "usd_per_aud"]
    fx["date"] = pd.to_datetime(fx["date"])
    fx = fx.dropna().set_index("date")["usd_per_aud"]
    rate = [fx.loc[:w].tail(5).mean() for w in df["week"]]
    df = df.assign(aud_usd=rate)
    df["product_usd_bbl"] = df["product_aucpl"] / 100 * df["aud_usd"] * LITRES_PER_BBL
    return df


def merge(new: pd.DataFrame) -> pd.DataFrame:
    """Accumulate: kept weeks outlive their deletion from the AIP server."""
    if OUT.exists():
        old = pd.read_csv(OUT, parse_dates=["week"])
        new = pd.concat([old, new], ignore_index=True)
    return new.drop_duplicates(["week", "fuel"], keep="last").sort_values(["fuel", "week"])


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
        print(f"! could not fetch the FX series ({exc}); store left unchanged", file=sys.stderr)
        return 0

    before = len(pd.read_csv(OUT)) if OUT.exists() else 0
    df = merge(priced)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    counts = df.groupby("fuel")["week"].agg(["count", "min", "max"])
    print(f"\nStored {len(df)} rows ({len(df) - before:+d}) -> {OUT.relative_to(REPO)}")
    for fuel, r in counts.iterrows():
        print(f"  {fuel:15s} {r['count']:3d} weeks  {r['min'].date()} .. {r['max'].date()}")

    print("\nLoad it and read the signals:")
    print("  dbt seed --select aip_singapore_weekly --full-refresh")
    print("  dbt build --select monitor_aip_gap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
