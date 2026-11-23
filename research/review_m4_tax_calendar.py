"""M4 of the 19 Nov 2026 review: what does a calendar of announced tax changes
buy the forecast?

`pipeline/backtest.py` predicts `d_taxes = 0` — "announced changes are
knowable in principle, but using them would be hindsight here". It is
hindsight only without the date each change was announced. With that date, a
change is public information at the run, and the forecast can carry it:

    d_retail = 1.15 * (d_net + d_taxes + d_ets),  d_taxes = sum of the changes
               landing in t+1..t+h that were announced by the run

The model's fit is untouched: `d_net` is net of taxes, so the calendar is an
additive term on the published call and nothing is refitted.

THE CALENDAR. Effective dates and amounts are MBIE's own: every change in
`taxes` of 0.5 c/L or more since 2010, which falls on one week or splits over
two by the day of the week it starts (1 Jul 2023, a Saturday: 2/7 then 5/7).
The term takes MBIE's realised weekly change in those weeks, so the split
between the two weeks is read, not derived — a mild look-ahead at h=1 only;
over two or more weeks the sum is the announced amount. Announcement dates are
from primary sources (below), and where a law and an earlier announcement
differ, the later, legally certain one is used, so the gain is a lower bound.

SUPERSEDED SCHEDULES. The 2022-23 excise cut was due to lapse four times and
was extended each time, announced 20 May 2022 (lapse 15 Jun), 17 Jul 2022
(15 Aug), 14 Dec 2022 (31 Jan) and 1 Feb 2023 (halving on 1 Mar). Every one
came more than three weeks plus a run before the lapse it cancelled, so a
calendar following the schedule in force at each run never forecasts a
restoration that did not happen within h <= 3. Not modelled for that reason.

The run date of the call at week t is t + 6 days: MBIE publishes week t on
the Wednesday after it ends and the chain loads it on the Thursday.

Usage:  python research/review_m4_tax_calendar.py
Offline. Same inputs as research/wf_harness.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wf_harness as wf

# effective date, fuels, what, known from, source
EVENTS = [
    ("2013-07-01", "petrol", "FED +3c", "2013-05-20",
     "Customs and Excise (Budget Measures—Motor Spirits) Amendment Act 2013, assent 20 May 2013 "
     "(Cabinet 20 Aug 2012): legislation.govt.nz/act/public/2013/24"),
    ("2014-07-01", "petrol", "FED +3c", "2013-05-20", "same Act, second of three steps"),
    ("2017-07-01", "petrol", "ACC petrol levy 6.9 -> 6.0c", "2016-12-31",
     "announced in 2016 for 'July 1 next year' (ODT, Nathan Guy); Gazette 2017-au1738. Day not found"),
    ("2018-07-01", "all", "Auckland RFT 10c", "2018-06-26",
     "Land Transport Management (Regional Fuel Tax) Amendment Act 2018, assent 26 Jun 2018"),
    ("2018-09-30", "petrol", "FED +3.5c", "2018-06-28",
     "Govt announcement 27-28 Jun 2018 (RNZ 28 Jun 2018); Order 2018/136"),
    ("2019-07-01", "petrol", "FED +3.5c (+0.3 PEFML)", "2018-06-28",
     "same announcement; Budget Measures Act 2019. PEFML notice date not found"),
    ("2020-07-01", "petrol", "FED +3.5c", "2018-06-28", "same announcement; Budget Measures Act 2019"),
    ("2022-03-15", "petrol", "FED -25c", "2022-03-15",
     "Customs: reduction started 15 Mar 2022; announced in March, day taken as the start"),
    ("2023-07-01", "petrol", "FED +25c restored", "2023-02-01",
     "extension to 30 Jun 2023 announced 1 Feb 2023 (RNZ, 1News); confirmed in Budget 2023"),
    ("2024-07-01", "all", "Auckland RFT ends", "2024-02-08",
     "PM announcement 8 Feb 2024 (RNZ); Repeal Act 2024, assent 7 Mar 2024"),
]


def calendar_term(d: pd.DataFrame, fuel: str) -> tuple[pd.Series, pd.Series]:
    """Per stamped week: the tax change the calendar attributes to it, and the
    date it became known. Weeks with no event: 0 and NaT."""
    d_tax = d.taxes.diff()
    amt = pd.Series(0.0, index=d.index)
    known = pd.Series(pd.NaT, index=d.index, dtype="datetime64[ns]")
    is_petrol = fuel != "Diesel"
    for eff, fuels, _, kf, _ in EVENTS:
        if fuels == "petrol" and not is_petrol:
            continue
        e = pd.Timestamp(eff)
        win = (d.index >= e - pd.Timedelta(days=2)) & (d.index <= e + pd.Timedelta(days=10)) \
            & (d_tax.abs() > 0.05).to_numpy()
        assert win.sum() in (1, 2), (fuel, eff, win.sum())
        amt[win] = d_tax[win]
        known[win] = pd.Timestamp(kf)
    # nothing of 0.5 c/L or more left outside the calendar from 2013
    rest = d_tax[(amt == 0) & (d.index >= "2013-01-01")].abs()
    assert rest.max() < 0.5, (fuel, rest.idxmax(), rest.max())
    return amt, known


def main() -> None:
    frames = wf.production_frames()
    res = wf.walk_forward(frames)
    rows = []
    for fuel, d in frames.items():
        amt, known = calendar_term(d, fuel)
        pos = {dt: i for i, dt in enumerate(d.index)}
        a, k = amt.to_numpy(), known.to_numpy()
        for r in res[res.fuel == fuel].itertuples():
            t = pos[r.date]
            run = r.date + pd.Timedelta(days=6)
            term, missed, touched = 0.0, 0.0, False
            for j in range(1, r.h + 1):
                if t + j >= len(d) or a[t + j] == 0:
                    continue
                touched = True
                if k[t + j] <= run:
                    term += a[t + j]
                else:
                    missed += a[t + j]
            rows.append((fuel, r.date, r.h, 1.15 * term, 1.15 * missed, touched))
    cal = pd.DataFrame(rows, columns=["fuel", "date", "h", "cal", "cal_unknown", "touched"])
    m = res.merge(cal, on=["fuel", "date", "h"])
    m = m[m.outcome_known & (m.date >= "2013-02-01")]
    m["nowcast_cal"] = m.nowcast + m.cal

    print("MAE in c/L on the pump price, every call since Feb 2013 with a known outcome.")
    print("'+cal' adds the announced tax changes known at the run.\n")
    print(f"{'fuel':20s} {'h':>2} {'n':>4} {'naive':>7} {'naive+cal':>9} {'nowcast':>8} {'+cal':>7} "
          f"{'gain':>6} | {'tax-week calls':>14} {'nowcast':>8} {'+cal':>7} {'unknown':>8}")
    for (fuel, h), g in m.groupby(["fuel", "h"]):
        mae = lambda s: s.abs().mean()
        tw = g[g.touched]
        print(f"{fuel:20s} {h:>2} {len(g):>4} {mae(g.actual):7.3f} {mae(g.actual - g.cal):9.3f} "
              f"{mae(g.actual - g.nowcast):8.3f} {mae(g.actual - g.nowcast_cal):7.3f} "
              f"{1 - mae(g.actual - g.nowcast_cal) / mae(g.actual - g.nowcast):6.1%} | "
              f"{len(tw):>14} {mae(tw.actual - tw.nowcast):8.2f} {mae(tw.actual - tw.nowcast_cal):7.2f} "
              f"{int((tw.cal_unknown != 0).sum()):>8}")

    print("\nCalls touching a tax week, h=1, Regular Petrol:")
    g = m[(m.fuel == "Regular Petrol") & (m.h == 1) & m.touched].copy()
    g["err"] = g.actual - g.nowcast
    g["err_cal"] = g.actual - g.nowcast_cal
    print(g[["target_date", "actual", "nowcast", "cal", "cal_unknown", "err", "err_cal"]].round(2).to_string(index=False))

    print("\nWhere the calendar did not know in time (all fuels, all h):")
    u = m[m.cal_unknown != 0]
    print(u[["fuel", "date", "h", "target_date", "cal", "cal_unknown"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
