"""Two curves: the model's error today, and its error knowing the week in progress.

Accumulated week by week through 2026, because that is the year a reader
remembers: five quiet weeks in January, then the Iran-US episode from 6
February. Cumulative rather than weekly, because a week-by-week error chart is
a sawtooth in which nothing is legible — and cumulative hides nothing, since a
week where the nowcast does worse shows up as the gap closing.

Reads `data/nowcast_results.csv`, written by
`research/nowcast_in_adl.py --save`.

Run from this directory: it reads `fonts/*.ttf` by relative path and writes
the PNG beside itself.
"""
import glob as _glob
from pathlib import Path as FsPath

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager as fm

for _f in _glob.glob("fonts/*.ttf"):
    fm.fontManager.addfont(_f)
DISPLAY, BODY = "Archivo", "IBM Plex Sans"
plt.rcParams["font.family"] = BODY
plt.rcParams["font.size"] = 10

INK, MUTED, GROUND, LINE = "#0E2126", "#5A6C70", "#EDF2F2", "#CFDADB"
CARD = "#FFFFFF"
NOW, WAS = "#B4530A", "#57A6B4"

ROOT = FsPath(__file__).parents[2]
FUEL, H, YEAR = "Regular Petrol", 2, 2026


def main() -> None:
    d = pd.read_csv(ROOT / "data" / "nowcast_results.csv", parse_dates=["date"])
    d = d[(d.fuel == FUEL) & (d.h == H) & d.outcome_known].dropna(
        subset=["adl_ecm", "adl_ecm_nc", "actual"])
    d = d[d.date.dt.year == YEAR].sort_values("date").reset_index(drop=True)
    d["was"] = (d.adl_ecm - d.actual).abs().cumsum()
    d["now"] = (d.adl_ecm_nc - d.actual).abs().cumsum()

    fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=200)
    fig.patch.set_facecolor(GROUND)
    ax.set_facecolor(CARD)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.grid(axis="y", color=LINE, lw=0.8)
    ax.set_axisbelow(True)

    # The episode opens on the first week the volatility mask is on. Drawn as
    # a marker rather than a shaded span: the episode runs to the end of the
    # data, so a band would colour four fifths of the chart and say nothing.
    onset = d.loc[d.hi.idxmax(), "date"] if d.hi.any() else None

    ax.plot(d.date, d.was, color=WAS, lw=2.8, label="Today's model")
    ax.plot(d.date, d.now, color=NOW, lw=2.8,
            label="Model + the week in progress")
    ax.fill_between(d.date, d.now, d.was, color=NOW, alpha=0.10, lw=0)

    if onset is not None:
        ax.axvline(onset, color=MUTED, lw=1.0, ls=(0, (4, 3)))
        # Left of the line, in January's empty space: to the right the curve
        # is climbing steeply and runs straight through the text.
        ax.text(onset - pd.Timedelta(days=5), ax.get_ylim()[1] * 0.10,
                "crude turns volatile,\n6 Feb", ha="right",
                fontsize=9.5, color=MUTED, va="bottom")

    gap = d.was.iloc[-1] - d.now.iloc[-1]
    pct = gap / d.was.iloc[-1] * 100
    print(f"sum |error|: was {d.was.iloc[-1]:.1f}, now {d.now.iloc[-1]:.1f}, "
          f"gap {gap:.1f} c/L over {len(d)} forecasts")
    ax.annotate("", xy=(d.date.iloc[-1], d.now.iloc[-1]),
                xytext=(d.date.iloc[-1], d.was.iloc[-1]),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.2))
    ax.text(d.date.iloc[-1] - pd.Timedelta(days=6),
            (d.was.iloc[-1] + d.now.iloc[-1]) / 2,
            f"{gap:.0f} c/L\nless error\nover the year\n({pct:.0f}%)",
            ha="right", va="center", fontsize=11, color=INK, linespacing=1.35)

    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    # Spelled out rather than shortened: "error piled up" reads equally well
    # as a running mean, and this is a running SUM of absolute errors.
    ax.set_ylabel("Sum of absolute forecast errors since January, c/L",
                  color=MUTED, labelpad=9)
    ax.tick_params(colors=MUTED, length=0)
    ax.set_title("Through the quiet weeks the two are the same line.\n"
                 "The 2026 crisis is where they part.",
                 fontfamily=DISPLAY, fontsize=17, color=INK, loc="left", pad=16)
    ax.legend(frameon=False, loc="upper left", fontsize=10.5)

    fig.text(0.012, 0.015,
             f"{FUEL}, two weeks ahead - one forecast made each week, so the "
             f"fortnights overlap - {len(d)} of them in {YEAR} - "
             "walk-forward, refit every week - NZ Fuel Price Project",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.035, 1, 1))
    out = FsPath(__file__).with_name("nowcast_error_2026.png")
    fig.savefig(out, facecolor=GROUND)
    print(f"-> {out}")
    print(f"total: was {d.was.iloc[-1]:.1f}, now {d.now.iloc[-1]:.1f} c/L")


if __name__ == "__main__":
    main()
