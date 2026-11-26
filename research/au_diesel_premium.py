"""Was diesel's 2026 post-crash excess regional (import costs) or New Zealand's own?

Written 26 Nov 2026 BEFORE the run. Seen before writing: only the AIP file's
header rows and its last row. Not seen: any 2026 Australian value.

Australia's wholesale terminal gate prices (AIP, national average, AUD c/L
incl. 10% GST and excise) price imports at Singapore parity, so a premium or
freight on diesel that the Asian cost models miss would show in them. Excise
is the same for petrol and diesel and changed several times in 2026, so the
test uses the diesel-minus-petrol difference, in which it cancels:

  AU(t) = (TGP_diesel - TGP_ULP) / 1.1
          - (ComCom diesel cost - ComCom 91 cost), tax-exclusive, NZD -> AUD
  NZ(t) = MBIE margin diesel - MBIE margin 91 (NZD c/L), for comparison

Weekly means over MBIE weeks (Monday-Sunday, stamped Friday).
Baseline: 6-27 Feb 2026, the four weeks before the conflict.
Window: 24 Apr - 10 Jul 2026, New Zealand's diesel excess window.

Rule, on AU's window mean minus its baseline:
  REGIONAL if +15 c/L or more (about half New Zealand's ~33 c/L diesel excess,
    in AUD);
  NEW ZEALAND'S OWN if within +/-5;
  PARTLY REGIONAL in between (or below -5: reported as is).
"""
# First run 26 Nov 2026 as a scratch script; moved here afterwards with only
# its inputs changed. The docstring above is the rule as written before that
# run. docs/research.md, "Australia's wholesalers did not hold diesel's margin".
#
# AIP's file: "Historical Petrol and Diesel TGP data", AIP_TGP_Data_<date>.xlsx,
# https://aip.com.au/pricing/terminal-gate-prices-wholesale/ - kept in data/aip/.
# FX: FRED DEXUSAL and DEXUSNZ, cached in data/fred/ and fetched if missing.
#
#   python research/au_diesel_premium.py --archive-date 2026-11-26
import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from diesel_crash_window import COMCOM_XLSX, ROOT, comcom_weekly, load   # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--archive-date", default="2026-11-26")
_ap.add_argument("--xlsx", default=str(COMCOM_XLSX))
_ap.add_argument("--tgp", default=str(ROOT / "data" / "aip" / "AIP_TGP_Data_20-Nov-2026.xlsx"))
ARGS = _ap.parse_args()
tgp_x = ARGS.tgp
fx_dir = ROOT / "data" / "fred"
for _sid in ("DEXUSAL", "DEXUSNZ"):
    _f = fx_dir / f"{_sid}.csv"
    if not _f.exists():
        fx_dir.mkdir(parents=True, exist_ok=True)
        _url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={_sid}&cosd=2026-01-01&coed=2026-11-25"
        with urllib.request.urlopen(_url, timeout=60) as r:
            _f.write_bytes(r.read())
_p, _ = load(ARGS.archive_date)


def sheet(name):
    wb = openpyxl.load_workbook(tgp_x, read_only=True, data_only=True)
    rows = list(wb[name].iter_rows(values_only=True))
    df = pd.DataFrame(rows[1:], columns=[str(c).split("\n")[0] for c in rows[0]])
    df = df.rename(columns={df.columns[0]: "date"}).dropna(subset=["date"])
    df["date"] = pd.to_datetime(df.date)
    return df.set_index("date")["National"].astype(float)


def weekly(s):
    wk = s.index - pd.to_timedelta(s.index.weekday, unit="D") + pd.Timedelta(days=4)
    return s.groupby(wk).mean()


ulp, dsl = sheet("Petrol TGP"), sheet("Diesel TGP")
fx = {}
for sid in ("DEXUSAL", "DEXUSNZ"):
    f = pd.read_csv(f"{fx_dir}/{sid}.csv", parse_dates=["observation_date"]).set_index("observation_date")[sid]
    fx[sid] = pd.to_numeric(f, errors="coerce")
nzd_to_aud = weekly((fx["DEXUSNZ"] / fx["DEXUSAL"]).dropna())

cc = comcom_weekly(_p, ARGS.xlsx)
ccd = cc[cc.fuel == "Diesel"].set_index("week").cc_cost_excl
ccp = cc[cc.fuel == "Regular Petrol"].set_index("week").cc_cost_excl
wp = _p.rename(columns={"Date": "week_date", "Fuel": "fuel"})
md = wp[wp.fuel == "Diesel"].set_index("week_date").importer_margin
mp = wp[wp.fuel == "Regular Petrol"].set_index("week_date").importer_margin

T = pd.DataFrame({"tgp_d_minus_u": weekly((dsl - ulp) / 1.1)})
T["cost_d_minus_p_aud"] = (ccd - ccp) * nzd_to_aud
T["AU"] = T.tgp_d_minus_u - T.cost_d_minus_p_aud
T["NZ"] = md - mp
T["tgp_ulp_ex_gst"] = weekly(ulp / 1.1)
T["tgp_dsl_ex_gst"] = weekly(dsl / 1.1)
T = T[(T.index >= "2026-01-30") & (T.index <= "2026-09-25")]

pd.set_option("display.width", 220)
print(T.round(1).to_string())
base = T[(T.index >= "2026-02-06") & (T.index <= "2026-02-27")]
win = T[(T.index >= "2026-04-24") & (T.index <= "2026-07-10")]
y25 = weekly((dsl - ulp) / 1.1)
y25 = y25[(y25.index >= "2025-01-01") & (y25.index < "2026-01-01")].mean()
print(f"\nAU: baseline {base.AU.mean():+.1f}, window {win.AU.mean():+.1f}, change {win.AU.mean() - base.AU.mean():+.1f} AUD c/L")
print(f"NZ: baseline {base.NZ.mean():+.1f}, window {win.NZ.mean():+.1f}, change {win.NZ.mean() - base.NZ.mean():+.1f} NZD c/L")
print(f"(reference: AU TGP diesel-minus-ULP ex GST, 2025 mean {y25:.1f}; Feb 2026 {base.tgp_d_minus_u.mean():.1f}; window {win.tgp_d_minus_u.mean():.1f})")
ch = win.AU.mean() - base.AU.mean()
v = "REGIONAL" if ch >= 15 else ("NEW ZEALAND'S OWN" if abs(ch) <= 5 else "PARTLY REGIONAL / reported as is")
print("RULE:", v)
