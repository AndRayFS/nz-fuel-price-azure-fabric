"""Animated anatomy of the NZ diesel price, monthly frames 2020 -> 2026.

Left column  : what the price is made of, in cents per litre.
Right column : average weekly change of each layer over the preceding six
               calendar months, also in cents per litre. Both columns are
               absolute and share a fixed scale across the whole clip, so the
               6x jump in weekly movement during 2026 is visible as height,
               not as a number in a caption.

Warm-up: the window needs six months, so the maths starts mid-2019 and the
first shown frame is Jan 2020.
"""
import pandas as pd, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import glob as _glob

for _f in _glob.glob("fonts/*.ttf"):
    fm.fontManager.addfont(_f)
DISPLAY, BODY, MONO = "Archivo", "IBM Plex Sans", "IBM Plex Mono"
plt.rcParams["font.family"] = BODY
plt.rcParams["font.size"] = 10
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Rectangle
from PIL import Image
from pathlib import Path as FsPath

ROOT = FsPath("/Users/Ray/nz-fuel-price-project/nz_fuel_price_project")
OUT = FsPath(".")
L = 158.987

INK, MUTED, GROUND, LINE = "#0E2126", "#5A6C70", "#EDF2F2", "#CFDADB"
CARD = "#FFFFFF"
COLS = {"Crude oil": "#0F3B47", "Refining + shipping": "#1B7086",
        "NZ chain + margin": "#57A6B4", "Fuel excise": "#7C8A8E",
        "Emissions (ETS)": "#9AA7AA", "GST": "#C3CCCD"}
ORDER = list(COLS)
ACCENT = "#B4530A"

p = pd.read_csv(ROOT / "research/data/panel_weekly.csv", parse_dates=["Date"])
p = p[p.Fuel == "Diesel"].set_index("Date").sort_index()
p["Crude oil"] = p.dubai_crude_nzd * 100 / L
p["Refining + shipping"] = p.importer_cost - p["Crude oil"]
p["NZ chain + margin"] = p.importer_margin
p["Fuel excise"] = p.taxes
p["Emissions (ETS)"] = p.ets
p["GST"] = p.gst

per = pd.read_csv(ROOT / "seeds/periods.csv", parse_dates=["start_date", "end_date"])
per = per[per.period_type == "crisis"]

months = pd.date_range("2020-01-31", "2026-08-31", freq="ME")
comp = p[ORDER].resample("ME").mean()
chg = p[ORDER].diff().abs().resample("ME").mean()          # mean |weekly change| per month
mov = chg.rolling(6).mean()                                 # six calendar months

LEFT_MAX = float(comp.loc["2020":].sum(axis=1).max()) * 1.005
RIGHT_MAX = float(mov.loc["2020":].sum(axis=1).max()) * 1.34

W, H = 10.0, 5.75
LX, RX, CW = 0.315, 0.645, 0.085          # axes fractions
TOP, BASE = 0.775, 0.272


def stack(vals, vmax):
    """Bottom coordinate and height per segment, in axes fraction.

    Negative layers (diesel's margin went below zero in Mar 2026, an all-time
    low) are drawn downward from the baseline rather than clipped, so the
    stack stays honest and the collapse is visible.
    """
    span = TOP - BASE
    out, y, ydown = [], BASE, BASE
    for v in vals:
        h = v / vmax * span
        if h >= 0:
            out.append((y, h))
            y += h
        else:
            ydown += h
            out.append((ydown, -h))
    return out


def title_frame():
    """Opening card. LinkedIn shows frame one as the preview, so it has to
    stand on its own before anyone presses play."""
    fig = plt.figure(figsize=(W, H), dpi=110)
    fig.patch.set_facecolor(GROUND)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.add_patch(Rectangle((0.040, 0.050), 0.920, 0.920, facecolor=CARD,
                           edgecolor=LINE, lw=1.0, zorder=-5))

    ax.text(0.5, 0.815, "What a litre of diesel", ha="center", fontsize=27,
            color=INK, fontfamily=DISPLAY)
    ax.text(0.5, 0.720, "is actually made of", ha="center", fontsize=27,
            color=INK, fontfamily=DISPLAY)
    ax.plot([0.42, 0.58], [0.665, 0.665], color=ACCENT, lw=2.5)

    ax.text(0.5, 0.600, "New Zealand, every month from 2020 to 2026",
            ha="center", fontsize=12.5, color=MUTED, fontfamily=BODY)

    ax.text(0.285, 0.470, "L E F T", ha="center", fontsize=10, color=INK,
            fontfamily=DISPLAY)
    ax.text(0.285, 0.415, "the six layers of the price,", ha="center",
            fontsize=11.5, color=MUTED, fontfamily=BODY)
    ax.text(0.285, 0.372, "in cents per litre", ha="center",
            fontsize=11.5, color=MUTED, fontfamily=BODY)

    ax.plot([0.5, 0.5], [0.335, 0.500], color=LINE, lw=1)

    ax.text(0.715, 0.470, "R I G H T", ha="center", fontsize=10, color=INK,
            fontfamily=DISPLAY)
    ax.text(0.715, 0.415, "how much each layer moved,", ha="center",
            fontsize=11.5, color=MUTED, fontfamily=BODY)
    ax.text(0.715, 0.372, "averaged over the previous six months", ha="center",
            fontsize=11.5, color=MUTED, fontfamily=BODY)

    for row, (names, ry) in enumerate(((ORDER[:3], 0.250), (ORDER[3:], 0.190))):
        x = 0.5 - (len(names) * 0.185) / 2
        for name in names:
            ax.add_patch(Rectangle((x, ry), 0.026, 0.030, facecolor=COLS[name], lw=0))
            ax.text(x + 0.034, ry + 0.015, name, fontsize=9.2, color=MUTED,
                    va="center", fontfamily=BODY)
            x += 0.185

    ax.text(0.5, 0.122, "Source: MBIE weekly fuel price monitoring",
            ha="center", fontsize=9, color=MUTED, fontfamily=MONO)

    fig.canvas.draw()
    img = Image.frombytes("RGBA", fig.canvas.get_width_height(),
                          bytes(fig.canvas.buffer_rgba())).convert("RGB")
    plt.close(fig)
    return img


LANE = [0.325, 0.385, 0.445, 0.505, 0.565, 0.625, 0.685, 0.745]


def frame(m):
    fig = plt.figure(figsize=(W, H), dpi=110)
    fig.patch.set_facecolor(GROUND)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.add_patch(Rectangle((0.040, 0.050), 0.920, 0.920, facecolor=CARD,
                           edgecolor=LINE, lw=1.0, zorder=-5))
    ax.plot([0.075, 0.925], [0.872, 0.872], color=LINE, lw=1, zorder=-4)

    # scale ceilings, so the empty space above a short stack reads as headroom
    for xa, vmax_, unit in ((LX, LEFT_MAX, "c/L"), (RX, RIGHT_MAX, "c/L / wk")):
        ax.plot([xa - 0.012, xa + CW + 0.012], [TOP, TOP], color="#A5B4B7", lw=0.8,
                ls=(0, (3, 4)), zorder=-3)
        ax.text(xa + CW + 0.018, TOP, f"top of scale  {vmax_:.0f} {unit}",
                fontsize=8.6, color="#8B9C9F", va="center", ha="left", fontfamily=MONO)

    cvals = comp.loc[m, ORDER].values
    mvals = mov.loc[m, ORDER].values
    ls, rs = stack(cvals, LEFT_MAX), stack(mvals, RIGHT_MAX)

    # ribbons
    for i, name in enumerate(ORDER):
        (y0, h0), (y1, h1) = ls[i], rs[i]
        x0, x1 = LX + CW, RX
        cx = (x0 + x1) / 2
        verts = [(x0, y0 + h0), (cx, y0 + h0), (cx, y1 + h1), (x1, y1 + h1),
                 (x1, y1), (cx, y1), (cx, y0), (x0, y0), (x0, y0 + h0)]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                 Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), facecolor=COLS[name],
                               alpha=0.30 if i < 3 else 0.09, lw=0))

    ax.plot([LX - 0.005, RX + CW + 0.005], [BASE, BASE], color=LINE, lw=1,
            zorder=0)

    # bars + labels
    taken, small = [], []
    for i, name in enumerate(ORDER):
        (y0, h0), (y1, h1) = ls[i], rs[i]
        ax.add_patch(Rectangle((LX, y0), CW, h0, facecolor=COLS[name], lw=0))
        ax.add_patch(Rectangle((RX, y1), CW, h1, facecolor=COLS[name], lw=0))
        yc = y0 + h0 / 2
        if h0 > 0.024:
            taken.append(yc)
            ax.text(LX - 0.014, yc, name, ha="right", va="center",
                    fontsize=11, color=INK, fontfamily=BODY)
            ax.text(LX + CW / 2, yc, f"{cvals[i]:+.0f}" if cvals[i] < 0
                    else f"{cvals[i]:.0f}", ha="center", va="center",
                    fontsize=10, color="white" if i < 2 else INK, fontfamily=MONO)
        else:
            small.append((i, name, yc))
        if h1 > 0.022:
            ax.text(RX + CW + 0.014, y1 + h1 / 2, f"{mvals[i]:.1f}", ha="left",
                    va="center", fontsize=10, color=MUTED, fontfamily=MONO)

    for i, name, yc in small:
        lane = next((l for l in LANE
                     if all(abs(l - t) > 0.042 for t in taken)), LANE[-1])
        taken.append(lane)
        ax.plot([LX - 0.010, LX - 0.046], [yc, lane], color=LINE, lw=0.8)
        ax.text(LX - 0.052, lane, f"{name}  {cvals[i]:.0f}", ha="right",
                va="center", fontsize=9.2, color=MUTED, fontfamily=BODY)

    ax.text(LX + CW / 2, 0.847, "W H A T   T H E   P R I C E   I S   M A D E   O F",
            ha="center", fontsize=10, color=INK, fontfamily=DISPLAY)
    ax.text(LX + CW / 2, 0.822, f"{m.strftime('%B %Y')}  ·  {cvals.sum():.0f} c/L",
            ha="center", fontsize=10, color=MUTED)
    ax.text(RX + CW / 2, 0.847, "W H A T ' S   B E E N   M O V I N G   I T", ha="center",
            fontsize=10, color=INK, fontfamily=DISPLAY)
    w0 = (m - pd.DateOffset(months=5)).strftime("%b %Y")
    ax.text(RX + CW / 2, 0.822,
            f"avg weekly change, c/L · {w0} – {m.strftime('%b %Y')}",
            ha="center", fontsize=10, color=MUTED, fontfamily=MONO)

    # timeline
    ty = 0.150
    t0, t1 = pd.Timestamp("2020-01-01"), pd.Timestamp("2026-09-30")
    def tx(d): return 0.075 + (d - t0) / (t1 - t0) * 0.85
    ax.plot([0.075, 0.925], [ty, ty], color=LINE, lw=2, solid_capstyle="butt")
    for _i, (_, r) in enumerate(per.iterrows()):
        end = r.end_date if pd.notna(r.end_date) else t1
        if end < t0: continue
        ax.plot([tx(max(r.start_date, t0)), tx(end)], [ty, ty], color=ACCENT,
                lw=5, solid_capstyle="butt", alpha=0.85)
        if m >= r.start_date:
            lane = ty + (0.030 if _i % 2 == 0 else 0.062)
            ax.text(tx(max(r.start_date, t0)), lane, r.period_name,
                    fontsize=9, color=ACCENT if m <= end else MUTED,
                    ha="left", va="bottom", fontfamily=BODY)
    for yr in range(2020, 2027):
        d = pd.Timestamp(f"{yr}-01-01")
        ax.plot([tx(d)], [ty], marker="|", color=MUTED, ms=8)
        ax.text(tx(d), ty - 0.045, str(yr), fontsize=9, color=MUTED, ha="center",
                fontfamily=MONO)
    ax.plot([tx(m)], [ty], marker="o", color=INK, ms=9, zorder=5)

    ax.text(0.075, 0.925, "NZ diesel, what a litre is made of — and what actually moves",
            fontsize=16, color=INK, fontfamily=DISPLAY)
    ax.text(0.075, 0.893, "Both columns in cents per litre, each on its own fixed scale "
            "held constant across the clip. Source: MBIE weekly fuel price monitoring.",
            fontsize=9.5, color=MUTED, fontfamily=BODY)

    fig.canvas.draw()
    img = Image.frombytes("RGBA", fig.canvas.get_width_height(),
                          bytes(fig.canvas.buffer_rgba())).convert("RGB")
    plt.close(fig)
    return img


frames = [title_frame()]
frames += [frame(m) for m in months if m in comp.index and not mov.loc[m].isna().any()]
print(f"{len(frames)} frames (1 title + {len(frames)-1} months), {frames[0].size}")
frames = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
dur = [210] * len(frames); dur[0] = 2600; dur[1] = 900; dur[-1] = 4600
frames[0].save(OUT / "fuel_price_anatomy.gif", save_all=True, append_images=frames[1:],
               duration=dur, loop=0, optimize=True)
print("size:", (OUT / "fuel_price_anatomy.gif").stat().st_size / 1e6, "MB")
