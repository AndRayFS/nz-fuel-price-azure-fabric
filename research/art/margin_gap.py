"""What a litre costs before anyone earns anything, and what it sells for.

The gap between the two lines is the whole story of September 2026: the
landed cost of a litre jumped, the pump followed a fraction of the way, and
the difference is sitting in a compressed importer margin.

The lower line is everything in a litre except the importer's margin — the
landed cost, fuel excise and ETS, with GST applied on top exactly as MBIE's
identity applies it. So it is the price at which an importer would break even,
and **the space between the two lines is the margin itself**, grossed up by
GST. Nothing is assumed or fitted: both lines are published numbers, and the
band closing is the compression, drawn rather than asserted.

Deliberately not a plot of cost against price: those sit on different levels
(159.7 against 302.2 c/L for petrol in the week of 11 Sep) and the space
between them is mostly tax, which is not news.

Colour is one accent plus ink, deliberately: these are not two peer
categories. The pump price is the subject and carries the ink; the break-even
is the reference and carries the accent, which also fills the band.

Reads `data/panel_weekly.csv`. Run from this directory; it reads `fonts/*.ttf`
by relative path. Offline; no warehouse, no capacity.
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
CARD, ACCENT = "#FFFFFF", "#B4530A"

ROOT = FsPath(__file__).parents[2]
NORM_WINDOW = 104
GST = 1.15
FROM = "2025-01-01"
PANELS = (("Regular Petrol", "Petrol 91"), ("Diesel", "Diesel"))


def series(fuel: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "panel_weekly.csv", parse_dates=["Date"])
    d = d[d.Fuel == fuel].sort_values("Date").reset_index(drop=True)
    # Trailing mean, shifted a week so a compressed week never sits in the
    # benchmark it is being judged against.
    d["norm"] = d.importer_margin.rolling(
        NORM_WINDOW, min_periods=NORM_WINDOW).mean().shift(1)
    # Everything but the margin, GST included. Checked: GST is 15% of the
    # other four components, exact to 0.01 c/L on every row, so this is the
    # published break-even and the residual is exactly margin x 1.15.
    d["breakeven"] = (d.importer_cost + d.taxes + d.ets) * GST
    return d[d.Date >= FROM]


def main() -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 8.4), dpi=200, sharex=True)
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

        ax.fill_between(s.Date, s.breakeven, s.adjusted_retail_price,
                        color=ACCENT, alpha=0.16, linewidth=0,
                        label="Importer margin")
        ax.plot(s.Date, s.breakeven, color=ACCENT, lw=2.0,
                label="Cost, excise, ETS and GST")
        ax.plot(s.Date, s.adjusted_retail_price, color=INK, lw=3.0,
                label="Actual pump price")

        # Label parked in clear space and led to the gap, rather than placed
        # on it — at this scale the two lines are a few pixels apart and any
        # label sitting between them lands on one of them.
        last = s.iloc[-1]
        gap = last.adjusted_retail_price - last.breakeven
        typical = last["norm"] * GST
        ax.annotate(f"margin {gap:.0f} c/L\nusually about {typical:.0f}",
                    xy=(last.Date, (last.breakeven + last.adjusted_retail_price) / 2),
                    xycoords="data",
                    xytext=(0.985, 0.97), textcoords="axes fraction",
                    ha="right", va="top", fontsize=10, color=INK,
                    fontfamily=DISPLAY,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=1.0,
                                    shrinkA=8, shrinkB=4))

        ax.set_title(label, fontfamily=DISPLAY, fontsize=15, color=INK,
                     loc="left", pad=8)
        ax.set_ylabel("cents per litre", color=MUTED)
        ax.tick_params(colors=MUTED, length=0)
        ax.margins(x=0.02)
        if ax is axes[0]:
            ax.legend(frameon=False, fontsize=10, loc="upper left",
                      bbox_to_anchor=(0.0, 1.0))

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    fig.suptitle("Everything in a litre except the margin — and the margin",
                 fontfamily=DISPLAY, fontsize=18, color=INK,
                 x=0.012, ha="left", y=0.985)
    fig.text(0.012, 0.012,
             "Lower line: landed cost, excise and ETS, plus GST. The band "
             "between the lines is the importer margin.  Weekly, MBIE",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.028, 1, 0.955))
    out = FsPath(__file__).with_name("margin_gap_2026.png")
    fig.savefig(out, facecolor=GROUND)
    print(f"-> {out}")
    for fuel, _ in PANELS:
        s = series(fuel)
        last = s.iloc[-1]
        print(f"{fuel}: {len(s)} weeks to {last.Date:%d %b %Y}; "
              f"pump {last.adjusted_retail_price:.1f}, break-even {last.breakeven:.1f}, "
              f"margin {last.adjusted_retail_price - last.breakeven:.1f} c/L "
              f"(two-year norm {last['norm'] * GST:.1f})")


if __name__ == "__main__":
    main()
