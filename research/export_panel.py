"""Export the weekly panel from Fabric to a local CSV, once.

Everything downstream of this (ADL/ECM estimation) runs offline against the
CSV. That is deliberate, not lazy:

  * estimation is a loop of twenty specifications, not one query — round
    trips to a warehouse would dominate the wall clock;
  * the F2 capacity bills real money from 28 Aug 2026 and auto-pauses at
    23:00 NZT, so research that needs it up is research that stalls;
  * the committed CSV makes every number in docs/ reproducible by anyone
    without an Azure subscription.

Auth mirrors ~/.dbt/profiles.yml (`authentication: CLI`): an Azure CLI
token, packed into the ODBC access-token attribute exactly the way
dbt-fabric's own token provider does it (fabric_token_provider.py:214-227).
Run `az login` first if this fails.

Usage:  python research/export_panel.py
"""

from __future__ import annotations

import struct
from itertools import chain, repeat
from pathlib import Path

import mssql_python
from azure.identity import AzureCliCredential

SERVER = (
    "fhi24zxnvquurfybnnzrkz22aq-ae4c5pcutjkedh2gfko4iqwk24"
    ".datawarehouse.fabric.microsoft.com"
)
DATABASE = "analytics_warehouse"
SQL_SCOPE = "https://database.windows.net/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256

OUT = Path(__file__).parent / "data" / "panel_weekly.csv"

# One row per (week, fuel). Brent columns ride along because they are free
# here and save a second round trip; they are diagnostics, not factors.
#
# Period assignment uses the first matching row of `periods` ordered by id:
# 01 ends and 02 starts on the same day (2020-06-05), so a plain join would
# duplicate that week.
QUERY = """
select
    f.Date,
    f.Fuel,
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
    br.brent_mean,
    br.brent_range,
    st.status,
    p.period_id,
    p.period_type
from dbo.silver_fuel f
join dbo.silver_general g
    on g.Date = f.Date
outer apply (
    select top 1 pp.period_id, pp.period_type
    from dbo.periods pp
    where cast(f.Date as date) >= pp.start_date
      and (pp.end_date is null or cast(f.Date as date) <= pp.end_date)
    order by pp.period_id
) p
-- Status is uniform across every variable within a week (checked): from
-- 3 Apr 2026 the whole row is Provisional, not just the two series MBIE
-- paused. It finalises when Stats NZ publishes the quarter's CPI.
outer apply (
    select top 1 r.Status as status
    from dbo.mbie_revisions r
    where r.Date = f.Date
) st
outer apply (
    select avg(b.brent_usd_bbl) as brent_mean,
           max(b.brent_usd_bbl) - min(b.brent_usd_bbl) as brent_range
    from dbo.brent_daily b
    where b.date between dateadd(day, -4, cast(f.Date as date))
                     and cast(f.Date as date)
) br
where f.Fuel in ('Regular Petrol', 'Diesel', 'Premium Petrol 95R')
order by f.Fuel, f.Date
"""


def connect():
    token = AzureCliCredential().get_token(SQL_SCOPE).token
    encoded = bytes(chain.from_iterable(zip(bytes(token, "UTF-8"), repeat(0))))
    token_bytes = struct.pack("<i", len(encoded)) + encoded
    # No DRIVER= clause: mssql-python bundles its own driver and rejects the
    # keyword outright ("Reserved keyword 'driver' is controlled by the
    # driver"). The `driver:` line in profiles.yml is consumed by dbt, not
    # passed through to the connection string.
    conn_str = (
        f"SERVER={SERVER},1433;DATABASE={DATABASE};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    return mssql_python.connect(
        conn_str,
        attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_bytes},
        autocommit=True,
    )


def main() -> None:
    import csv

    with connect() as conn:
        cur = conn.cursor()
        cur.execute(QUERY)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)

    print(f"{len(rows)} rows -> {OUT}")
    if rows:
        print(f"columns: {', '.join(cols)}")


if __name__ == "__main__":
    main()
