"""Page 3, Margin, written as PBIR: each fuel's importer margin against its own
two-year average, week by week, and where the price of a litre goes."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
M, P = "margin_compression", "prices"
FUELS = [("Regular Petrol", "Regular 91", "#40B54A", 70), ("Premium Petrol 95R", "Premium 95", "#E5C700", 74),
         ("Diesel", "Diesel", "#4D4C48", 40)]
LEFT, RIGHT = (24, 132, 748, 520), (788, 132, 468, 520)
GREY, PALE_ORANGE, PALE_GREY, BAND, BAND_EDGE = "#A3A29B", "#F6BFA8", "#DEDDD7", "#F1F0EC", "#E2E1DB"
# Left-hand chart heights in proportion to each fuel's range of gaps (with and without
# MBIE's adjustment, plus the axis margins) on 23 Oct 2026: 73, 76 and 169 c/L.
# No chart draws a date axis: Power BI drops it on a chart this short, and the one
# chart tall enough to keep it reserved a margin for it and ended its plot ~19 px
# short of the others (4 Nov review). The two end dates are written under diesel
# instead - the axis always runs from the first week to the newest, so they never drift.
GAP_BLOCKS = [(64, 79), (175, 82), (289, 183)]
# (measure stem, legend label, colour this week, colour on average, label colour this week)
PARTS = [("Cost", "Importer cost", "#5C5B56", "#CFCECA", PAPER), ("Taxes", "Taxes and levies", "#A3A29B", "#DFDED9", INK),
         ("ETS", "Emissions trading", "#C9C8C1", "#E8E7E2", INK), ("GST", "GST", "#DEDDD7", "#EFEEEA", INK),
         ("Margin", "Importer margin", ORANGE, "#F8D2C2", INK)]
LABELLED = {"Cost", "Taxes", "GST"}    # ETS and the margin are too thin to carry a label; the margin's is on the right

def gap_layer(layer):
    """One of three column charts drawn on one another on the same axis: 'band' for
    the weeks MBIE suspended, 'pale' spanning the gap with and without MBIE's
    adjustment, 'dark' for the part both agree on. Only the top layer's axis labels
    show; the lower layers write theirs in white on the white card, so all three keep
    the same plot area."""
    S = lambda m: {"metadata": f"{M}.{m}"}
    top = layer == "dark"
    if layer == "band":
        series = [("Band Up (chart)", BAND), ("Band Down (chart)", BAND)]
    elif layer == "pale":
        series = [("Gap Pale Up (chart)", PALE_GREY), ("Gap Pale Down (chart)", PALE_ORANGE)]
    else:
        series = [("Gap Dark (chart)", None)]
    ink = col(FAINT if top else PAPER)
    v = {"visualType": "clusteredColumnChart" if top else "columnChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Week", "week", "Week", active=True)]},
            "Y": {"projections": [proj("m", M, m, m) for m, _ in series]}},
            "sortDefinition": {"sort": [{"field": cref("Week", "week"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            "dataPoint": [obj({"fill": mcol(M, "Gap Colour (chart)")}, {"data": [{"dataViewWildcard": {"matchingOption": 1}}]})] if top
                         else [obj({"fill": col(fill)}, S(m)) for m, fill in series],
            "categoryAxis": [obj({"show": b(False), "axisType": s("Scalar"), "showAxisTitle": b(False), "gridlineShow": b(False),
                                  "innerPadding": L(0 if layer == "band" else 20)})],
            "valueAxis": [obj({"show": b(True), "start": mexpr(M, "Gap Axis Low"), "end": mexpr(M, "Gap Axis High"),
                               "showAxisTitle": b(False), "gridlineShow": b(layer == "pale"), "gridlineColor": col("#ECEBE6"),
                               "fontSize": d(8), "labelColor": ink})],
            "legend": [obj({"show": b(False)})],
            "labels": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    if top:
        # The mock-up's zero line, in ink.
        v["objects"]["y1AxisReferenceLine"] = [obj({"show": b(True), "displayName": s("Average"), "value": d(0),
                                                    "lineColor": col(INK), "style": s("solid"), "width": d(1),
                                                    "dataLabelShow": b(False)}, {"id": "1"})]
    return v

def share_chart(layer):
    """The parts of a litre as a stacked bar, two rows: this week and the average,
    on one c/L scale for every fuel. Drawn twice: this week's row dark, the average's
    pale. The labels are shares of the price, from the measures' format strings."""
    S = lambda m: {"metadata": f"{P}.{m}"}
    now = layer == "now"
    names = [f"{k} Bar ({layer})" for k, *_ in PARTS]
    return {"visualType": "barChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Share Row", "Kind", "Kind", active=True)]},
            "Y": {"projections": [proj("m", P, n, part[1]) for n, part in zip(names, PARTS)]}},
            "sortDefinition": {"sort": [{"field": cref("Share Row", "Kind"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            "dataPoint": [obj({"fill": col(full if now else pale)}, S(n)) for n, (_, _, full, pale, _) in zip(names, PARTS)],
            "labels": [obj({"show": b(True), "fontSize": d(8)})] + [
                obj({"showSeries": b(k in LABELLED), "color": col(ink if now else MUTED)}, S(n))
                for n, (k, _, _, _, ink) in zip(names, PARTS)],
            # Thick enough for an 8 pt label: at 30 the bars came out ~10 px and the labels hid.
            "categoryAxis": [obj({"show": b(False), "innerPadding": L(8)})],
            "valueAxis": [obj({"show": b(False), "start": d(0), "end": mexpr(P, "Share Axis End"), "gridlineShow": b(False)})],
            "legend": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def key(items, x, y, z, prefix, size=9):
    """A row of swatches and labels: (label, label width, list of marks as (w, h, dy, fill[, border]))."""
    V = []
    for k, (text, lw, marks) in enumerate(items):
        mx = x
        for j, (w, h, dy, fill, *border) in enumerate(marks):
            V.append(container(f"{prefix}{k}m{j}", mx, y + dy, w, h, z, blank(fill, border=border[0] if border else None)))
            mx += w + (2 if h > 2 else 3)
        V.append(container(f"{prefix}{k}t", mx + 4, y - 3, lw, 20, z, textbox([[(text, size, MUTED, False)]])))
        x = mx + 4 + lw + 12
    return V

def page_margin():
    V = header()
    V.append(container("headline", 24, 60, 1232, 64, 100, title_shape(P, "Margin Headline", 17)))

    x, y, w, h = LEFT; z = 200
    V += [container("lbg", x, y, w, h, z, blank(PAPER, border=LINE, radius=8)),
          container("ltitle", x + 16, y + 12, w - 32, 24, z + 1, textbox([[(
              "Importer margin against its own two-year average, c/L, weekly since 29 Mar 2024", 12, INK, True)]]))]
    V += key([("Below its average", 96, [(10, 10, 1, ORANGE)]),
              ("Above", 34, [(10, 10, 1, GREY)]),
              ("Shift from MBIE's cost adjustment, 27 Feb – 11 Sep", 272, [(5, 10, 1, PALE_ORANGE), (5, 10, 1, PALE_GREY)]),
              ("Suspended by MBIE, filled in later", 184, [(14, 10, 1, BAND, BAND_EDGE)])],
             x + 16, y + 42, z + 2, "lk")
    for i, ((key_, label, colour, uw), (dy, ch)) in enumerate(zip(FUELS, GAP_BLOCKS)):
        by = y + dy; f = [fuel_filter(key_)]; zz = z + 20 + i * 10
        V += [container(f"g{i}name", x + 14, by, 200, 22, zz, textbox([[(label, 10.5, INK, True)]])),
              container(f"g{i}uline", x + 16, by + 22, uw, 3, zz + 1, blank(colour)),
              container(f"g{i}date", x + w - 160, by + 4, 100, 18, zz + 2, title_text(M, "Gap Header Date", 9, MUTED, align="right"), f),
              container(f"g{i}value", x + w - 58, by + 2, 42, 20, zz + 2,
                        title_text(M, "Gap Header Value", 9.75, INK, bold=True, align="right"), f)]
        V += [container(f"g{i}{layer}", x + 8, by + 26, w - 16, ch, zz + 3 + k, gap_layer(layer), f)
              for k, layer in enumerate(("band", "pale", "dark"))]
    by = y + GAP_BLOCKS[2][0] + 26 + GAP_BLOCKS[2][1]
    V += [container("gfrom", x + 34, by, 120, 14, z + 60, textbox([[("29 Mar 2024", 8, FAINT, False)]])),
          container("gto", x + w - 170, by - 2, 160, 16, z + 60, title_text(M, "Gap Last Week", 8, FAINT, align="right"))]
    by = y + GAP_BLOCKS[0][0] + 26 + GAP_BLOCKS[0][1]
    V.append(container("g0nosplit", x + w - 236, by - 18, 220, 16, z + 60, {
        "visualType": "textbox", "objects": {"general": [obj({"paragraphs": [{"horizontalTextAlignment": "right", "textRuns": [
            {"value": "after 11 Sep: no split", "textStyle": {"fontFamily": FONT, "fontSize": "7.5pt", "color": FAINT,
                                                              "fontStyle": "italic"}}]}]})]},
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}))

    x, y, w, h = RIGHT; z = 300
    V += [container("rbg", x, y, w, h, z, blank(PAPER, border=LINE, radius=8)),
          container("rtitle", x + 16, y + 12, w - 32, 44, z + 1, title_shape(P, "Share Title", 12)),
          container("rsub", x + 16, y + 58, w - 32, 30, z + 2, title_shape(P, "Share Subtitle", 8.25, MUTED, bold=False)),
          container("rmhead", x + w - 76, y + 92, 60, 16, z + 2, textbox([[("Margin", 8.25, FAINT, False)]], align="right"))]
    for i, (key_, label, colour, uw) in enumerate(FUELS):
        by = y + 104 + i * 118; f = [fuel_filter(key_)]; zz = z + 10 + i * 12
        V += [container(f"s{i}name", x + 14, by, 200, 22, zz, textbox([[(label, 10.5, INK, True)]])),
              container(f"s{i}uline", x + 16, by + 22, uw, 3, zz + 1, blank(colour)),
              container(f"s{i}date", x + 16, by + 39, 104, 16, zz + 2, title_text(P, "Share Date", 8.25, MUTED), f),
              container(f"s{i}pnow", x + 16, by + 52, 104, 18, zz + 2, title_text(P, "Share Price Now", 9, INK, bold=True), f),
              container(f"s{i}avg", x + 16, by + 68, 104, 16, zz + 2, textbox([[("Average", 8.25, MUTED, False)]])),
              container(f"s{i}pavg", x + 16, by + 81, 104, 18, zz + 2, title_text(P, "Share Price Average", 9, MUTED), f),
              container(f"s{i}pale", x + 124, by + 26, w - 200, 84, zz + 3, share_chart("average"), f),
              container(f"s{i}dark", x + 124, by + 26, w - 200, 84, zz + 4, share_chart("now"), f),
              container(f"s{i}mnow", x + w - 76, by + 45, 60, 20, zz + 5,
                        title_text(P, "Margin Share Now Label", 9.75, INK, bold=True, align="right"), f),
              container(f"s{i}mavg", x + w - 76, by + 74, 60, 20, zz + 5,
                        title_text(P, "Margin Share Average Label", 9.75, MUTED, align="right"), f)]
    V.append(container("rdiesel", x + 16, y + 104 + 2 * 118 + 112, w - 32, 18, z + 50, textbox([[(
        "Diesel's road taxes are paid as road user charges, outside the pump price.", 8.25, MUTED, False)]])))
    swatches = [(label, lw, [(10, 10, 1, full)]) for (_, label, full, _, _), lw in zip(PARTS, (72, 88, 96, 26, 96))]
    V += key(swatches[:3], x + 16, y + h - 44, z + 60, "sk", size=8.25)
    V += key(swatches[3:], x + 16, y + h - 26, z + 60, "sl", size=8.25)

    V.append(container("footer", 24, 662, 1232, 40, 400, textbox([[(
        "The margin is what is left of the pump price after taxes and MBIE's estimate of this week's replacement cost, "
        "so a jump in cost squeezes it at once. A squeeze does not say whether the pump price or the cost closes it.",
        8.25, FAINT, False)]])))
    return V

write_page(ROOT, "p3margin", "Margin", page_margin())
pages = json.loads((ROOT / "pages/pages.json").read_text())
order = [p for p in pages["pageOrder"] if p != "p3margin"]
order.insert(order.index("p2track") + 1, "p3margin")
pages["pageOrder"] = order
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(page_margin()), "visuals on Margin")
