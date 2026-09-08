"""What the two models actually called, in cents per litre, through 2026.

Three lines per fuel: what the pump price did, what today's model said it
would do two weeks earlier, and what the same model said once it was told how
the week already under way was going.

Each forecast is plotted against the week it was a call FOR, not the week it
was made — otherwise a two-week-ahead line sits two weeks to the left of the
thing it is predicting and every lead looks like a lag.

Reads `data/nowcast_results.csv` from `research/nowcast_in_adl.py --save`.
Run from this directory; it reads `fonts/*.ttf` by relative path.
"""
import glob as _glob
from pathlib import Path as FsPath

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager as fm

for _f in _glob.glob("fonts/*.ttf"):
    fm.fontManager.addfont(_f)
DISPLAY, BODY = "Archivo", "IBM Plex Sans"
plt.rcParams["font.family"] = BODY
plt.rcParams["font.size"] = 10

INK, MUTED, GROUND, LINE = "#0E2126", "#5A6C70", "#EDF2F2", "#CFDADB"
CARD, ACTUAL, WAS, NOW = "#FFFFFF", "#0E2126", "#57A6B4", "#B4530A"

ROOT = FsPath(__file__).parents[2]
H, YEAR = 2, 2026
PANELS = (("Regular Petrol", "Petrol"), ("Diesel", "Diesel"))


def series(fuel: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "nowcast_results.csv",
                    parse_dates=["date", "target_date"])
    d = d[(d.fuel == fuel) & (d.h == H) & d.outcome_known].dropna(
        subset=["adl_ecm", "adl_ecm_nc", "actual", "target_date"])
    d = d[d.target_date.dt.year == YEAR].sort_values("target_date")
    return pd.DataFrame({
        "week": d.target_date,
        "actual": d.price_now + d.actual,
        "was": d.price_now + d.adl_ecm,
        "now": d.price_now + d.adl_ecm_nc,
    })


def main() -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 8.6), dpi=200, sharex=True)
    fig.patch.set_facecolor(GROUND)

    for ax, (fuel, label) in zip(axes, PANELS):
        s = series(fuel)
        ax.set_facecolor(CARD)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(LINE)
        ax.grid(axis="y", color=LINE, lw=0.8)
        ax.set_axisbelow(True)

        ax.plot(s.week, s.actual, color=ACTUAL, lw=3.0, label="Actual price")
        ax.plot(s.week, s.was, color=WAS, lw=2.0,
                label="Today's model, called 2 weeks earlier")
        ax.plot(s.week, s.now, color=NOW, lw=2.0,
                label="Same model + the week in progress")

        ax.set_title(label, fontfamily=DISPLAY, fontsize=15, color=INK,
                     loc="left", pad=8)
        ax.set_ylabel("c/L", color=MUTED)
        ax.tick_params(colors=MUTED, length=0)
        if ax is axes[0]:
            ax.legend(frameon=False, fontsize=10, loc="upper left")

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    fig.suptitle("Two weeks ahead, through the 2026 crisis",
                 fontfamily=DISPLAY, fontsize=18, color=INK,
                 x=0.012, ha="left", y=0.985)
    fig.text(0.012, 0.012,
             "Each forecast plotted on the week it was a call for - "
             "walk-forward, the model refit every week - NZ Fuel Price Project",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.028, 1, 0.955))
    out = FsPath(__file__).with_name("nowcast_levels_2026.png")
    fig.savefig(out, facecolor=GROUND)
    print(f"-> {out}")
    for fuel, _ in PANELS:
        s = series(fuel)
        print(f"{fuel}: {len(s)} weeks, {s.week.min():%d %b} .. {s.week.max():%d %b}, "
              f"price {s.actual.min():.0f}-{s.actual.max():.0f} c/L")


if __name__ == "__main__":
    main()
