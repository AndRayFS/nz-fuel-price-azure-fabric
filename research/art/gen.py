"""Build the Sankey SVGs for the fuel-price anatomy page."""

LAYERS = [
    ("Crude oil",              "l1", True),
    ("Refining + shipping",    "l2", True),
    ("NZ chain + margin",      "l3", True),
    ("Fuel excise",            "l4", False),
    ("Emissions (ETS)",        "l5", False),
    ("GST 15%",                "l6", False),
]

DATA = {
 "calm":   {"price": 200.9, "weeks": 156, "label": "Calm markets, 2023-2025",
            "share": [80.7, 30.0, 45.5, 2.7, 15.9, 26.2],
            "move":  [2.12, 1.51, 2.63, 0.02, 0.54, 0.23]},
 "crisis": {"price": 294.9, "weeks": 24, "label": "Crisis, Mar-Aug 2026",
            "share": [104.0, 88.5, 49.5, 1.0, 13.5, 38.5],
            "move":  [10.75, 14.36, 16.40, 0.01, 0.34, 2.04]},
}

W, H = 940, 500
TOP, BOT = 74, 468
COL_H = BOT - TOP
LX, RX, CW = 300, 640, 74          # left column x, right column x, column width
GAP = 3
MIN_H = 3.5


def column(values, total):
    """Segment tops and heights, scaled to the column with fixed gaps."""
    usable = COL_H - GAP * (len(values) - 1)
    raw = [max(v / total * usable, MIN_H) for v in values]
    scale = (usable - sum(r for r in raw if r == MIN_H)) / max(
        sum(r for r in raw if r != MIN_H), 1e-9)
    hs = [r if r == MIN_H else r * scale for r in raw]
    tops, y = [], TOP
    for h in hs:
        tops.append(y)
        y += h + GAP
    return tops, hs


def svg(key):
    d = DATA[key]
    st, sh = column(d["share"], sum(d["share"]))
    mt, mh = column(d["move"], sum(d["move"]))
    move_total = sum(d["move"])
    out = [
        f'<svg viewBox="0 0 {W} {H}" role="img" class="sankey" '
        f'aria-label="{d["label"]}: how the pump price splits into layers, and how much '
        f'each layer moves week to week">'
    ]
    out.append(f'<text x="{LX + CW/2:.0f}" y="42" class="colhead" text-anchor="middle">'
               'WHAT THE PRICE IS MADE OF</text>')
    out.append(f'<text x="{RX + CW/2:.0f}" y="42" class="colhead" text-anchor="middle">'
               'WHAT ACTUALLY MOVES</text>')
    out.append(f'<text x="{LX + CW/2:.0f}" y="58" class="colsub" text-anchor="middle">'
               f'{d["price"]:.0f} c/L average</text>')
    out.append(f'<text x="{RX + CW/2:.0f}" y="58" class="colsub" text-anchor="middle">'
               f'{move_total:.0f} c/L moves per week</text>')

    # ribbons first, so the solid bars sit on top of them
    for i, (name, cls, market) in enumerate(LAYERS):
        x0, x1 = LX + CW, RX
        t0, b0 = st[i], st[i] + sh[i]
        t1, b1 = mt[i], mt[i] + mh[i]
        cx = (x0 + x1) / 2
        out.append(
            f'<path class="rib {cls}" d="M{x0},{t0:.1f} C{cx},{t0:.1f} {cx},{t1:.1f} '
            f'{x1},{t1:.1f} L{x1},{b1:.1f} C{cx},{b1:.1f} {cx},{b0:.1f} {x0},{b0:.1f} Z"/>')

    for i, (name, cls, market) in enumerate(LAYERS):
        pct_l = d["share"][i] / sum(d["share"]) * 100
        pct_r = d["move"][i] / move_total * 100
        out.append(f'<rect class="bar {cls}" x="{LX}" y="{st[i]:.1f}" width="{CW}" '
                   f'height="{sh[i]:.1f}" rx="2"/>')
        out.append(f'<rect class="bar {cls}" x="{RX}" y="{mt[i]:.1f}" width="{CW}" '
                   f'height="{mh[i]:.1f}" rx="2"/>')
        ly = st[i] + sh[i] / 2
        out.append(f'<text x="{LX - 14}" y="{ly + 4:.1f}" class="lab" text-anchor="end">'
                   f'{name}</text>')
        if sh[i] > 15:
            out.append(f'<text x="{LX - 14}" y="{ly + 19:.1f}" class="val" text-anchor="end">'
                       f'{d["share"][i]:.0f} c/L &#183; {pct_l:.0f}%</text>')
        ry = mt[i] + mh[i] / 2
        if mh[i] > 13:
            out.append(f'<text x="{RX + CW + 14}" y="{ry + 4:.1f}" class="val" '
                       f'text-anchor="start">{pct_r:.0f}%</text>')
    return "\n".join(out) + "\n</svg>"


for k in DATA:
    open(f"sankey_{k}.svg.part", "w").write(svg(k))
    print(f"{k}: written, {len(svg(k))} chars")
