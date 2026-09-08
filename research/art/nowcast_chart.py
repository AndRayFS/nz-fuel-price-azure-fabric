"""Two curves: the model's error today, and its error knowing the week in progress.

Sorted by how much the pump price actually moved that fortnight, because that
is where the difference lives — the average hides it. Reads
`data/nowcast_results.csv`, written by `research/nowcast_in_adl.py --save`.

Run from this directory: it reads `fonts/*.ttf` by relative path and writes
the PNG beside itself.
"""
import glob as _glob
from pathlib import Path as FsPath

import matplotlib
matplotlib.use("Agg")
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
FUEL, H, BANDS = "Regular Petrol", 2, 10


def main() -> None:
    d = pd.read_csv(ROOT / "data" / "nowcast_results.csv", parse_dates=["date"])
    d = d[(d.fuel == FUEL) & (d.h == H) & d.outcome_known].dropna(
        subset=["adl_ecm", "adl_ecm_nc", "actual"])
    d["band"] = pd.qcut(d.actual.abs(), BANDS, labels=False, duplicates="drop")

    g = d.groupby("band").apply(lambda s: pd.Series({
        "was": np.abs(s.adl_ecm - s.actual).mean(),
        "now": np.abs(s.adl_ecm_nc - s.actual).mean(),
        "move": s.actual.abs().mean(),
    }), include_groups=False)

    fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=200)
    fig.patch.set_facecolor(GROUND)
    ax.set_facecolor(CARD)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.grid(axis="y", color=LINE, lw=0.8)
    ax.set_axisbelow(True)

    x = np.arange(1, len(g) + 1)
    ax.plot(x, g.was, "-o", color=WAS, lw=2.6, ms=6,
            label="Today's model")
    ax.plot(x, g.now, "-o", color=NOW, lw=2.6, ms=6,
            label="Model + the week in progress")

    top = len(g)
    ax.annotate("", xy=(top, g.now.iloc[-1]), xytext=(top, g.was.iloc[-1]),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.2))
    gain = (1 - g.now.iloc[-1] / g.was.iloc[-1]) * 100
    # Left of the arrow, not on it: the two lines converge here and a label
    # sitting between them lands on top of the upper one.
    ax.text(top - 0.25, (g.now.iloc[-1] + g.was.iloc[-1]) / 2,
            f"{gain:.0f}%\nless\nerror", ha="right", va="center",
            fontsize=11.5, color=INK, linespacing=1.35)

    ax.set_xticks(x)
    # One decimal, because the lower deciles round to the same integer and a
    # tick sequence reading 0, 1, 1, 2, 2 is worse than no labels at all.
    ax.set_xticklabels([f"{v:.1f}" for v in g.move])
    ax.set_xlabel("How much the pump price actually moved over the fortnight, "
                  "c/L  (weeks grouped into tenths)", color=MUTED, labelpad=9)
    ax.set_ylabel("Average forecast error, c/L", color=MUTED, labelpad=9)
    ax.tick_params(colors=MUTED, length=0)

    ax.set_title("In a quiet week it changes nothing.\n"
                 "In the weeks that move, it takes a fifth off the error.",
                 fontfamily=DISPLAY, fontsize=17, color=INK,
                 loc="left", pad=16)
    ax.legend(frameon=False, loc="upper left", fontsize=10.5)

    fig.text(0.012, 0.015,
             f"{FUEL}, two weeks ahead · {len(d)} weeks, 2013-2026 · "
             "walk-forward, refit every week · NZ Fuel Price Project",
             fontsize=8.5, color=MUTED)

    fig.tight_layout(rect=(0, 0.035, 1, 1))
    out = FsPath(__file__).with_name("nowcast_error_by_move.png")
    fig.savefig(out, facecolor=GROUND)
    print(f"-> {out}")
    print(g.round(2).to_string())


if __name__ == "__main__":
    main()
