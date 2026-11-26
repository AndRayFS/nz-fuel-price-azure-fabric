"""Did Perth's service stations hold diesel's retail margin after the April 2026 crash?

Written 26 Nov 2026 BEFORE the run. Seen before writing: the FuelWatch files'
columns and categories (retail: PRODUCT_DESCRIPTION ULP / Diesel / Brand Diesel
/ ..., REGION_DESCRIPTION Metro / ...; wholesale: TERMINAL_GATE, LOCATION incl.
KWINANA BEACH and KEWDALE, PRODUCT ULP / Diesel / PULP) and the AIP wholesale
test (national TGP diesel-minus-ULP premium over ComCom's cost difference rose
+8.3 AUD c/L, baseline to window, against New Zealand's diesel-minus-91 margin
+30.9 NZD c/L). Not seen: any FuelWatch price, any AIP Perth value.

The AIP test covered the wholesale layer only. New Zealand's importer margin is
the whole chain, terminal to pump, so the retail layer is the part still
missing. FuelWatch (WA government) publishes every station's daily price and
every terminal's daily TGP.

  Retail(f, day)  = mean over Metro (Perth) stations, PRODUCT_DESCRIPTION
                    "ULP" or "Diesel" (not "Brand Diesel"), AUD c/L incl. GST
  TGP(f, day)     = mean over the Perth terminals (LOCATION KWINANA BEACH or
                    KEWDALE), PRODUCT "ULP" or "Diesel"
  M(f)            = (Retail - TGP) / 1.1, the retail margin ex GST
  R(t)            = M(Diesel) - M(ULP)           <- scored
  C(t)            = (Retail_D - Retail_U) / 1.1
                    - (ComCom diesel - 91 cost, tax-exclusive) x NZD->AUD
                    the whole Perth chain, comparable with New Zealand's
                    diesel-minus-91 importer margin (reported, not scored)

Excise is equal for both fuels and moved on the same days (1 Apr, 1 Jul,
3 Aug 2026), so in R and C it cancels, apart from any difference in how fast
the two fuels' stocks turn over.

GST basis of FuelWatch's TGP, decided before any margin is computed: if its
Feb 2026 Perth mean is within 3% of AIP's Perth TGP, it includes GST (as AIP's
does); if within 3% of AIP / 1.1, it excludes GST and TGP is multiplied by 1.1
first; otherwise the run stops.

Weekly means over MBIE weeks (Monday-Sunday, stamped Friday).
Baseline: 6-27 Feb 2026. Window: 24 Apr - 10 Jul 2026 (as in the AIP test).

Rule, on R's window mean minus its baseline mean (AUD c/L):
  HELD AT RETAIL TOO if +10 or more (with the wholesale +8.3, the Perth chain
    would then reach about two thirds of New Zealand's change in AUD);
  NOT HELD AT RETAIL if within +/-5;
  PARTLY in between (below -5: reported as is).
Reported, not scored: M per fuel; C and C over New Zealand's change in AUD;
R on stations that price both fuels the same day; R with the median station.
"""
# First run 26 Nov 2026 as a scratch script; moved here afterwards with only
# its inputs changed. The docstring above is the rule as written before that
# run. docs/research.md, "Perth's service stations held diesel for four weeks".
#
# FuelWatch (WA): monthly retail files FuelWatchRetail-MM-2026.csv and
# FuelWatchWholesale-2026.csv, from
# https://warsydprdstafuelwatch.blob.core.windows.net/historical-reports/ -
# kept in data/fuelwatch/ (February to August retail; wholesale to 25 Nov).
# AIP's TGP file and FRED's FX as in research/au_diesel_premium.py.
#
#   python research/au_perth_retail.py --archive-date 2026-11-26
import argparse
import glob
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from diesel_crash_window import COMCOM_XLSX, ROOT, comcom_weekly, load   # noqa: E402

_ap = argparse.ArgumentParser()
_ap.add_argument("--archive-date", default="2026-11-26")
_ap.add_argument("--xlsx", default=str(COMCOM_XLSX))
_ap.add_argument("--tgp", default=str(ROOT / "data" / "aip" / "AIP_TGP_Data_20-Nov-2026.xlsx"))
_ap.add_argument("--fuelwatch", default=str(ROOT / "data" / "fuelwatch"))
ARGS = _ap.parse_args()
fw_dir, aip_x, fx_dir = ARGS.fuelwatch, ARGS.tgp, ROOT / "data" / "fred"
_p, _ = load(ARGS.archive_date)


def weekly(s):
    wk = s.index - pd.to_timedelta(s.index.weekday, unit="D") + pd.Timedelta(days=4)
    return s.groupby(wk).mean()


# --- retail
r = pd.concat([pd.read_csv(f, low_memory=False) for f in sorted(glob.glob(f"{fw_dir}/FuelWatchRetail-*-2026.csv"))])
r = r[(r.REGION_DESCRIPTION == "Metro") & r.PRODUCT_DESCRIPTION.isin(["ULP", "Diesel"])].copy()
r["day"] = pd.to_datetime(r.PUBLISH_DATE, format="%d/%m/%Y")
r["prod"] = r.PRODUCT_DESCRIPTION.map({"ULP": "U", "Diesel": "D"})
r = r.drop_duplicates(["day", "ADDRESS", "prod"])
ret_mean = r.groupby(["day", "prod"]).PRODUCT_PRICE.mean().unstack()
ret_med = r.groupby(["day", "prod"]).PRODUCT_PRICE.median().unstack()
both = r.pivot_table(index=["day", "ADDRESS"], columns="prod", values="PRODUCT_PRICE").dropna()
ret_matched_gap = both.groupby("day").apply(lambda x: (x.D - x.U).mean())

# --- wholesale
w = pd.read_csv(f"{fw_dir}/FuelWatchWholesale-2026.csv", low_memory=False)
w = w[w.LOCATION.isin(["KWINANA BEACH", "KEWDALE"]) & w.PRODUCT.isin(["ULP", "Diesel"])].copy()
w["day"] = pd.to_datetime(w.PUBLISH_DATE, format="%d/%m/%Y")
w["prod"] = w.PRODUCT.map({"ULP": "U", "Diesel": "D"})
tgp = w.groupby(["day", "prod"]).PRODUCT_PRICE.mean().unstack()


# --- GST basis check against AIP Perth
def aip(name):
    wb = openpyxl.load_workbook(aip_x, read_only=True, data_only=True)
    rows = list(wb[name].iter_rows(values_only=True))
    df = pd.DataFrame(rows[1:], columns=[str(c).split("\n")[0] for c in rows[0]])
    df = df.rename(columns={df.columns[0]: "date"}).dropna(subset=["date"])
    df["date"] = pd.to_datetime(df.date)
    return df.set_index("date")["Perth"].astype(float)


aipP = pd.DataFrame({"U": aip("Petrol TGP"), "D": aip("Diesel TGP")})
feb = (tgp.index >= "2026-02-01") & (tgp.index <= "2026-02-28")
fa = (aipP.index >= "2026-02-01") & (aipP.index <= "2026-02-28")
ratio = (tgp[feb].mean() / aipP[fa].mean())
print("FuelWatch Perth TGP / AIP Perth TGP, Feb 2026 means:", ratio.round(4).to_dict())
if ((ratio - 1).abs() <= 0.03).all():
    basis = "incl. GST"
elif ((ratio - 1 / 1.1).abs() <= 0.03).all():
    basis = "excl. GST -> x1.1"
    tgp = tgp * 1.1
else:
    sys.exit("GST basis undecided: stop")
print("GST basis of FuelWatch TGP:", basis)
both_days = tgp.index.intersection(aipP.index)
print("mean |FuelWatch - AIP| Perth TGP, all 2026 days, c/L:",
      (tgp.loc[both_days] - aipP.loc[both_days]).abs().mean().round(2).to_dict())

# --- FX, ComCom, NZ
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

# --- weekly
T = pd.DataFrame({
    "M_D": weekly((ret_mean.D - tgp.D).dropna() / 1.1),
    "M_U": weekly((ret_mean.U - tgp.U).dropna() / 1.1),
})
T["R"] = T.M_D - T.M_U
T["R_matched"] = weekly(((ret_matched_gap - (tgp.D - tgp.U)).dropna()) / 1.1)
T["R_median"] = weekly((((ret_med.D - tgp.D) - (ret_med.U - tgp.U)).dropna()) / 1.1)
T["W_perth"] = weekly((tgp.D - tgp.U).dropna() / 1.1) - (ccd - ccp) * nzd_to_aud
T["C"] = weekly((ret_mean.D - ret_mean.U).dropna() / 1.1) - (ccd - ccp) * nzd_to_aud
T["NZ"] = md - mp
T["NZ_aud"] = T.NZ * nzd_to_aud
T = T[(T.index >= "2026-02-06") & (T.index <= "2026-08-28")]

pd.set_option("display.width", 220)
print(T.round(1).to_string())
base = T[(T.index >= "2026-02-06") & (T.index <= "2026-02-27")]
win = T[(T.index >= "2026-04-24") & (T.index <= "2026-07-10")]
ch = win.mean() - base.mean()
print("\nbaseline mean:", base.mean().round(1).to_dict())
print("window mean:  ", win.mean().round(1).to_dict())
print("change:       ", ch.round(1).to_dict())
print(f"\nPerth chain C change {ch.C:+.1f} AUD = wholesale (Perth TGP) {ch.W_perth:+.1f} + retail R {ch.R:+.1f}; "
      f"NZ change {ch.NZ:+.1f} NZD = {ch.NZ_aud:+.1f} AUD; C / NZ_aud = {ch.C / ch.NZ_aud:.2f}")
v = ("HELD AT RETAIL TOO" if ch.R >= 10 else
     "NOT HELD AT RETAIL" if abs(ch.R) <= 5 else
     "PARTLY" if ch.R > 5 else "below -5: reported as is")
print(f"RULE: R change {ch.R:+.1f} AUD c/L -> {v}")
