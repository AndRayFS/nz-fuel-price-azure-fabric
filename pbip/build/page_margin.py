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
# (measure stem, legend label, colour this week, colour on average, label colour this week)
PARTS = [("Cost", "Importer cost", "#5C5B56", "#CFCECA", PAPER), ("Taxes", "Taxes", "#A3A29B", "#DFDED9", INK),
         ("ETS", "ETS", "#C9C8C1", "#E8E7E2", INK), ("GST", "GST", "#DEDDD7", "#EFEEEA", INK),
         ("Margin", "Importer margin", ORANGE, "#F8D2C2", INK)]
LABELLED = {"Cost", "Taxes", "GST"}    # ETS and the margin are too thin to carry a label; the margin's is on the right

def gap_chart(x_labels):
    """Weekly gap to the norm as columns coloured by a measure; the gap before
    MBIE's adjustment as a dashed line over 27 Feb - 11 Sep. One axis for all fuels."""
    G, B = "Gap (chart)", "Gap Before Adjustment (chart)"
    S = lambda m: {"metadata": f"{M}.{m}"}
    return {"visualType": "lineClusteredColumnComboChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Week", "week", "Week", active=True)]},
            "Y": {"projections": [proj("m", M, G, "Gap to the average")]},
            "Y2": {"projections": [proj("m", M, B, "Before MBIE's adjustment")]}},
            "sortDefinition": {"sort": [{"field": cref("Week", "week"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            "dataPoint": [obj({"fill": mcol(M, "Gap Colour (chart)")}, {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}),
                          obj({"fill": col(INK)}, S(B))],
            "lineStyles": [obj({"strokeWidth": d(1.5), "lineStyle": s("dashed"), "showMarker": b(False)}, S(B))],
            "categoryAxis": [obj({"show": b(x_labels), "axisType": s("Scalar"), "showAxisTitle": b(False), "gridlineShow": b(False),
                                  "fontSize": d(8), "labelColor": col(FAINT), "innerPadding": L(20)})],
            "valueAxis": [obj({"show": b(True), "start": mexpr(M, "Gap Axis Low"), "end": mexpr(M, "Gap Axis High"),
                               "showAxisTitle": b(False), "gridlineShow": b(True), "gridlineColor": col("#ECEBE6"),
                               "fontSize": d(8), "labelColor": col(FAINT), "secShow": b(False)})],
            "legend": [obj({"show": b(False)})],
            "labels": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def share_chart(layer):
    """Shares of the price as a stacked bar, two rows: this week and the average.
    Drawn twice on a fixed 0-100% axis: this week's row dark, the average's pale."""
    S = lambda m: {"metadata": f"{P}.{m}"}
    now = layer == "now"
    names = [f"{k} Share ({layer})" for k, *_ in PARTS]
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
            "valueAxis": [obj({"show": b(False), "start": d(0), "end": d(1), "gridlineShow": b(False)})],
            "legend": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def key(items, x, y, z, prefix, size=9):
    """A row of swatches and labels: (label, label width, list of marks as (w, h, dy, fill))."""
    V = []
    for k, (text, lw, marks) in enumerate(items):
        mx = x
        for j, (w, h, dy, fill) in enumerate(marks):
            V.append(container(f"{prefix}{k}m{j}", mx, y + dy, w, h, z, blank(fill)))
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
    V += key([("Below its average", 98, [(10, 10, 1, ORANGE)]),
              ("Above", 36, [(10, 10, 1, "#A3A29B")]),
              ("Filled in later by MBIE", 128, [(5, 10, 1, "#F6BFA8"), (5, 10, 1, "#DEDDD7")]),
              ("Before MBIE's cost adjustment, 27 Feb – 11 Sep", 262, [(4, 2, 5, INK), (4, 2, 5, INK), (4, 2, 5, INK)])],
             x + 16, y + 44, z + 2, "lk")
    for i, ((key_, label, colour, uw), (by, ch, xl)) in enumerate(zip(FUELS, [(y + 70, 104, False), (y + 206, 104, False),
                                                                            (y + 342, 140, True)])):
        f = [fuel_filter(key_)]; zz = z + 20 + i * 10
        V += [container(f"g{i}name", x + 14, by, 200, 22, zz, textbox([[(label, 10.5, INK, True)]])),
              container(f"g{i}uline", x + 16, by + 22, uw, 3, zz + 1, blank(colour)),
              container(f"g{i}head", x + w - 216, by + 4, 200, 18, zz + 2, title_text(M, "Gap Header", 9, MUTED, align="right"), f),
              container(f"g{i}chart", x + 8, by + 28, w - 16, ch, zz + 3, gap_chart(xl), f)]

    x, y, w, h = RIGHT; z = 300
    V += [container("rbg", x, y, w, h, z, blank(PAPER, border=LINE, radius=8)),
          container("rtitle", x + 16, y + 12, w - 32, 44, z + 1, textbox([[(
              "Where each litre goes: the newest week against the average since 29 Mar 2024", 12, INK, True)]])),
          container("rsub", x + 16, y + 58, w - 32, 18, z + 2, textbox([[(
              "Shares of the pump price · newest week dark, average pale", 9, MUTED, False)]])),
          container("rmhead", x + w - 76, y + 82, 60, 16, z + 2, textbox([[("Margin", 8.25, FAINT, False)]], align="right"))]
    for i, (key_, label, colour, uw) in enumerate(FUELS):
        by = y + 96 + i * 112; f = [fuel_filter(key_)]; zz = z + 10 + i * 12
        V += [container(f"s{i}name", x + 14, by, 200, 22, zz, textbox([[(label, 10.5, INK, True)]])),
              container(f"s{i}uline", x + 16, by + 22, uw, 3, zz + 1, blank(colour)),
              container(f"s{i}now", x + 16, by + 45, 112, 18, zz + 2, title_text(P, "Share Label Now", 8.25, INK, bold=True), f),
              container(f"s{i}avg", x + 16, by + 65, 112, 18, zz + 2, title_text(P, "Share Label Average", 8.25, MUTED), f),
              container(f"s{i}pale", x + 130, by + 30, w - 206, 60, zz + 3, share_chart("average"), f),
              container(f"s{i}dark", x + 130, by + 30, w - 206, 60, zz + 4, share_chart("now"), f),
              container(f"s{i}mnow", x + w - 76, by + 45, 60, 18, zz + 5,
                        title_text(P, "Margin Share Now Label", 9, INK, bold=True, align="right"), f),
              container(f"s{i}mavg", x + w - 76, by + 65, 60, 18, zz + 5,
                        title_text(P, "Margin Share Average Label", 9, MUTED, align="right"), f)]
    V.append(container("rdiesel", x + 16, y + 96 + 2 * 112 + 92, w - 32, 18, z + 50, textbox([[(
        "Diesel's road taxes are paid as road user charges, outside the pump price.", 8.25, MUTED, False)]])))
    V += key([(label, lw, [(10, 10, 1, full)]) for (_, label, full, _, _), lw in zip(PARTS, (74, 34, 24, 24, 86))],
             x + 16, y + h - 26, z + 60, "sk", size=8.25)

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
