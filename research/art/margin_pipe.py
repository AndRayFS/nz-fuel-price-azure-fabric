"""The importer margin drawn as a pipe: its width at any week IS the margin.

The companion chart (`margin_gap.py`) plots the pump price against the
break-even and leaves the margin as the gap between them. That is honest but
it asks the reader to measure a difference between two large numbers by eye,
at the bottom of a 400 c/L axis. Here the difference is the subject: a band
centred on zero whose full thickness is the margin in cents per litre, so
"the margin halved" is a pipe that visibly halves.

The dashed outline is the same margin's own trailing two-year mean, drawn the
same way. Inside the outline is a compressed margin; outside it, a fat one.

THE Y AXIS IS DELIBERATELY UNLABELLED. Each edge sits at half the margin, and
a reader who reads a tick as the margin would halve every number on the chart.
Widths are given as direct labels instead, and the caption says what the
thickness means.

NEGATIVE WEEKS ARE REAL AND ARE DRAWN AS THEY FALL. Four weeks in March and
April 2026 have a margin below zero — importers selling under their own landed
cost. The band crosses itself there rather than being clipped to zero, because
clipping would hide the most extreme fact in the series.

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
CARD = "#FFFFFF"

# The report's pump-nozzle colours (green 91, grey diesel), two steps deeper.
# As published they are `#40B54A` and `#cccccc`, which carry 2.6:1 and 1.6:1
# against white — fine for a button, unreadable as a large fill. Hue and
# identity are unchanged; only the step moved. Red is a status colour here and
# nothing else uses it: it marks the weeks the margin was below zero.
PETROL, DIESEL, BELOW = "#349B3E", "#7C8A8E", "#C1272D"

ROOT = FsPath(__file__).parents[2]
NORM_WINDOW = 104
GST = 1.15
FROM = "2025-01-01"
PANELS = (("Regular Petrol", "Petrol 91", PETROL),
          ("Diesel", "Diesel", DIESEL))
# The same three weeks on both panels, so the two can be read against each
# other: the deepest pinch, the one in late July, and the latest published week.
MARKS = ("2026-03-13", "2026-07-24", "2026-09-11")


def series(fuel: str) -> pd.DataFrame:
    d = pd.read_csv(ROOT / "data" / "panel_weekly.csv", parse_dates=["Date"])
    d = d[d.Fuel == fuel].sort_values("Date").reset_index(drop=True)
    d["norm"] = d.importer_margin.rolling(
        NORM_WINDOW, min_periods=NORM_WINDOW).mean().shift(1)
    # GST-inclusive, so the numbers match what the pump-price chart shows.
    d["margin"] = d.importer_margin * GST
    d["normw"] = d["norm"] * GST
    return d[d.Date >= FROM]


def label(ax, when, width, text, dy, ha="center"):
    """Direct width label with a short leader to the pipe's upper edge."""
    ax.annotate(text, xy=(when, width / 2), xycoords="data",
                xytext=(0, dy), textcoords="offset points",
                ha=ha, va="bottom" if dy > 0 else "top",
                fontsize=10, color=INK, fontfamily=DISPLAY,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=1.0,
                                shrinkA=2, shrinkB=3))


def main() -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9.2, 7.6), dpi=200, sharex=True)
    fig.patch.set_facecolor(GROUND)

    for ax, (fuel, name, hue) in zip(axes, PANELS):
        s = series(fuel)
        ax.set_facecolor(CARD)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(LINE)

        lo, hi, neg = -s.margin / 2, s.margin / 2, s.margin < 0
        # Each fill is labelled with its own fuel, so the legend carries both
        # colours; the shared entries are labelled once, on the first panel.
        ax.fill_between(s.Date, lo, hi, where=~neg, interpolate=True,
                        color=hue, alpha=0.8, linewidth=0, label=name)
        ax.fill_between(s.Date, lo, hi, where=neg, interpolate=True,
                        color=BELOW, alpha=0.9, linewidth=0,
                        label="Below zero" if ax is axes[0] else None)
        ax.plot(s.Date, s.normw / 2, color=MUTED, lw=1.2, ls=(0, (4, 3)),
                label="Two-year average" if ax is axes[0] else None)
        ax.plot(s.Date, -s.normw / 2, color=MUTED, lw=1.2, ls=(0, (4, 3)))
        ax.axhline(0, color=CARD, lw=0.8, zorder=3)

        # Dated labels, because "the April dip" and "the July one" are how the
        # post refers to them and a reader should be able to find both.
        for when, dy, ha in zip(MARKS, (-40, -40, 30),
                                ("center", "center", "right")):
            r = s.set_index("Date").loc[when]
            stamp = pd.Timestamp(when).strftime("%-d %b")
            # A margin of -0.4 prints as "-0", which reads as a typo; below a
            # cent the sign is the whole message and the number adds nothing.
            text = (f"{stamp}\nbelow zero" if -1 < r.margin < 0
                    else f"{stamp}\n{r.margin:.0f} c/L")
            label(ax, pd.Timestamp(when), r.margin, text, dy, ha)

        ax.set_title(name, fontfamily=DISPLAY, fontsize=15, color=INK,
                     loc="left", pad=8)
        ax.set_yticks([])
        ax.tick_params(colors=MUTED, length=0)
        ax.margins(x=0.02, y=0.30)

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    fig.suptitle("What the importer keeps, week by week",
                 fontfamily=DISPLAY, fontsize=18, color=INK,
                 x=0.012, ha="left", y=0.985)
    # Legend at figure level: inside the axes it sits on the band, and the
    # band is the one thing on this chart that must stay unobstructed.
    pairs = {}
    for ax in axes:
        for handle, text in zip(*ax.get_legend_handles_labels()):
            pairs.setdefault(text, handle)
    order = [PANELS[0][1], PANELS[1][1], "Below zero", "Two-year average"]
    fig.legend([pairs[k] for k in order if k in pairs],
               [k for k in order if k in pairs],
               frameon=False, fontsize=10, ncol=4,
               loc="upper left", bbox_to_anchor=(0.010, 0.945))
    fig.text(0.012, 0.012,
             "The band's full thickness is the importer margin in cents per "
             "litre, GST included. Where it crosses itself the margin was "
             "negative.  Weekly, MBIE",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.03, 1, 0.915))
    out = FsPath(__file__).with_name("margin_pipe_2026.png")
    fig.savefig(out, facecolor=GROUND)
    print(f"-> {out}")
    for fuel, _, _hue in PANELS:
        s = series(fuel)
        print(f"{fuel}: {s.margin.iloc[0]:.1f} -> {s.margin.iloc[-1]:.1f} c/L, "
              f"min {s.margin.min():.1f} ({s.loc[s.margin.idxmin()].Date:%d %b %Y}), "
              f"norm now {s.normw.iloc[-1]:.1f}")


if __name__ == "__main__":
    main()
