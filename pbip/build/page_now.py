"""Page 1, Now, and the hidden headline test page, written as PBIR."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
FUELS = [("Regular Petrol", "Regular 91", "#40B54A", 78),
         ("Premium Petrol 95R", "Premium 95", "#E5C700", 82),
         ("Diesel", "Diesel", "#4D4C48", 46)]
CARD_X = [24, 440, 856]; CARD_W = 400
# The cost pressure bars' tooltip page. The default tooltip listed the bars' own
# values, a scaled share; the figures above them already say what matters, so the
# tooltip names the fuel and nothing else.
TIP, TIP_SIZE = "p1tipfuel", (130, 34)
# Type for the headline and the three prices. A was kept on 4 Nov 2026 after B, light
# for both, was tried side by side; B is still on the hidden Fonts page.
STYLES = {"A": dict(head=FONT_B, num=FONT_B), "B": dict(head="Segoe UI Light", num="Segoe UI Light")}

def price_chart(key):
    S = lambda e, m: {"metadata": f"{e}.{m}"}
    PAID, AGO, AGOIN, LAST, CALLM = (("prices", "Paid (chart)"), ("prices", "Four Weeks Ago (chart)"),
                                     ("prices", "Four Weeks Ago Inner (chart)"), ("prices", "Latest (chart)"),
                                     ("forecast_accuracy", "Call (chart)"))
    return {"visualType": "lineChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Week", "week", "Week", active=True)]},
            "Y": {"projections": [proj("m", *PAID, "Average paid"), proj("m", *CALLM, "Model's calls"),
                                  proj("m", *LAST, "Newest week"), proj("m", *AGO, "Four weeks ago"),
                                  proj("m", *AGOIN, "Four weeks ago, inner")]}},
            "sortDefinition": {"sort": [{"field": cref("Week", "week"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            "dataPoint": [obj({"fill": col(INK)}, S(*PAID)), obj({"fill": col(CALL_LINE)}, S(*CALLM)),
                          obj({"fill": col(INK)}, S(*LAST)), obj({"fill": col(INK)}, S(*AGO)), obj({"fill": col(PAPER)}, S(*AGOIN))],
            "lineStyles": [
                obj({"strokeWidth": d(2), "lineChartType": s("smooth"), "showMarker": b(False)}, S(*PAID)),
                obj({"strokeWidth": d(2), "lineChartType": s("smooth"), "lineStyle": s("dashed"), "showMarker": b(True), "markerShape": s("circle"),
                     "markerSize": d(4), "markerColor": col(CALL_LINE)}, S(*CALLM)),
                obj({"strokeWidth": d(0), "showMarker": b(True), "markerShape": s("circle"), "markerSize": d(5), "markerColor": col(INK)}, S(*LAST)),
                obj({"strokeWidth": d(0), "showMarker": b(True), "markerShape": s("circle"), "markerSize": d(5), "markerColor": col(INK)}, S(*AGO)),
                obj({"strokeWidth": d(0), "showMarker": b(True), "markerShape": s("circle"), "markerSize": d(3), "markerColor": col(PAPER)}, S(*AGOIN))],
            "error": [
                obj({"enabled": b(True), "barShow": b(False), "shadeShow": b(True)}, S(*CALLM)),
                obj({"errorRange": {"kind": "ErrorRange", "explicit": {
                        "isRelative": b(False),
                        "upperBound": mexpr("forecast_accuracy", "Call High (chart)"),
                        "lowerBound": mexpr("forecast_accuracy", "Call Low (chart)")}}},
                    {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": "forecast_accuracy.Call (chart)", "highlightMatching": 1})],
            "xAxisReferenceLine": [obj({"show": b(True), "displayName": s("Today"), "value": mexpr("prices", "Today"),
                                        "lineColor": col(INK), "style": s("dashed"), "width": d(1), "dataLabelShow": b(False)}, {"id": "1"})],
            "categoryAxis": [obj({"show": b(True), "axisType": s("Scalar"), "showAxisTitle": b(False), "gridlineShow": b(False),
                                  "fontSize": d(8), "labelColor": col(FAINT)})],
            "valueAxis": [obj({"show": b(True), "showAxisTitle": b(False), "gridlineShow": b(True),
                               "gridlineColor": col("#ECEBE6"), "fontSize": d(8), "labelColor": col(FAINT)})],
            "legend": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

PRESSURE_PAD = 66    # innerPadding of each bar's chart: ~6 px bars; tuned on the dev copy
PRESSURE_H = 54      # a bar chart under ~50 px high draws a placeholder icon instead (44 did)

def pressure_chart(measure, colour):
    """One bar on a fixed 0..100 axis: this week's margin or its two-year average,
    scaled by Margin Scale, one scale for the three fuels, in Margin's colours. One
    chart per bar, not two rows in one: the gap between the bars is then where the
    charts sit, not a padding that also sets their thickness."""
    return {"visualType": "barChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Fuel", "Fuel name", "Fuel", active=True)]},
            "Y": {"projections": [proj("m", "margin_compression", measure, "Margin")]}}},
        "objects": {
            "dataPoint": [obj({"fill": col(colour)})],
            "valueAxis": [obj({"show": b(False), "start": d(0), "end": d(100), "gridlineShow": b(False)})],
            "categoryAxis": [obj({"show": b(False), "showAxisTitle": b(False), "innerPadding": L(PRESSURE_PAD)})],
            "legend": [obj({"show": b(False)})],
            "labels": [obj({"show": b(False)})],
        },
        "visualContainerObjects": dict(chrome(padding=(0, 0, 0, 0)),
            visualTooltip=[obj({"show": b(True), "type": s("Canvas"), "section": s(TIP)})]),
        "drillFilterOtherVisuals": True}

def legend(z):
    """Legend marks drawn as shapes, at the weights the chart uses: a 2 px line, a
    dashed 2 px line, a ring, a band, a dashed hairline. Glyphs in a text box came
    out at the font's stroke weight instead (review of 4 Nov 2026)."""
    V, x, y = [], 24, 140
    def label(name, text, w):
        V.append(container(name, x, y - 3, w, 20, z + len(V), textbox([[(text, 9, MUTED, False)]])))
    V.append(container("lg1", x, y + 6, 18, 2, z, blank(INK))); x += 24
    label("lg1t", "Average paid", 80); x += 84
    V.append(container("lg2", x, y, 10, 10, z + 1, blank(PAPER, border=INK, radius=5))); x += 16
    label("lg2t", "Four weeks ago", 92); x += 100
    for k in range(3):
        V.append(container(f"lg3{k}", x + k * 7, y + 6, 4, 2, z + 2, blank(CALL_LINE)))
    x += 24
    label("lg3t", "Model's calls", 80); x += 86
    V.append(container("lg4", x, y, 14, 10, z + 3, blank("#C3D9F3"))); x += 20
    label("lg4t", "Range of its past misses (middle half)", 220); x += 226
    for k in range(3):
        V.append(container(f"lg5{k}", x + 5, y + k * 5, 1, 3, z + 4, blank(INK)))
    x += 14
    label("lg5t", "Today", 40)
    return V

def page_now(style):
    V = header()
    z = 100
    V.append(container("headline", 24, 60, 1232, 64, z, title_shape("prices", "Headline", 17, face=style["head"])))
    V += legend(z + 10)
    V.append(container("period", CARD_X[2], 130, CARD_W, 34, z + 3, button_slicer("Period", "Period", "'6M'", 5)))
    for i, (key, label, colour, uw) in enumerate(FUELS):
        x = CARD_X[i]; z = 200 + i * 20; f = [fuel_filter(key)]
        V += [
            # 342 high, 352 until 23 Nov 2026: the 10 px went to air under the margin bars.
            container(f"c{i}bg", x, 172, CARD_W, 342, z, blank(PAPER, border=LINE, radius=8)),
            container(f"c{i}name", x + 14, 178, 220, 24, z + 1, textbox([[(label, 11, INK, True)]])),
            container(f"c{i}uline", x + 16, 203, uw, 3, z + 2, blank(colour)),
            container(f"c{i}weekto", x + 16, 212, 368, 18, z + 3, title_text("prices", "Week To Label", 8.25, MUTED)),
            container(f"c{i}price", x + 16, 230, 96, 38, z + 4, title_text("prices", "Price Now Number", 21, INK, face=style["num"]), f),
            # One space after the number and on its baseline, as in the mock-up: at x+92, y 244
            # it sat ~7 px off and ~4 px high (5 Nov 2026). Segoe UI's digits are all one width.
            container(f"c{i}unit", x + 89, 245, 40, 20, z + 4, textbox([[("c/L", 9.75, MUTED, False)]])),
            container(f"c{i}pill", x + 206, 238, 180, 26, z + 5, fx_box("prices", "Change 4w Fill"), f),
            container(f"c{i}arrow", x + 212, 242, 16, 20, z + 6,
                      title_text("prices", "Change 4w Arrow", 9, colour_measure=("prices", "Change 4w Colour")), f),
            container(f"c{i}change", x + 228, 242, 110, 20, z + 6, title_text("prices", "Change 4w Main", 9, INK, bold=True), f),
            container(f"c{i}weeks", x + 330, 242, 50, 20, z + 6, title_label("4 weeks", 9, MUTED, align="right")),
            container(f"c{i}chart", x + 6, 272, 388, 178, z + 6, price_chart(key), f),
            container(f"c{i}rule", x + 16, 456, 368, 1, z + 7, blank("#ECEBE6")),
        ] + [c for n in (1, 2, 3) for c in (
            container(f"c{i}d{n}", x + 16 + (n - 1) * 123, 464, 120, 18, z + 8,
                      title_text("forecast_accuracy", f"Call Date {n}", 8.25, FAINT), f),
            container(f"c{i}v{n}", x + 16 + (n - 1) * 123, 482, 120, 28, z + 8,
                      title_text("forecast_accuracy", f"Call {n}", 11.25, CALL, bold=True), f))]
    z = 300
    # "Importer margin", not "Cost pressure" (until 23 Nov 2026): the old name was true only
    # below the average, and the heading says in words what that means.
    # The note starts ~10 px after the name and sits 1 px higher than it did, on the
    # name's baseline (measured on the dev copy, 23 Nov 2026).
    V.append(container("cphead", 24, 522, 130, 22, z, textbox([[("Importer margin", 10.5, INK, True)]])))
    V.append(container("cpnote", 138, 525, 1118, 18, z + 1, title_text("margin_compression", "Cost Pressure Heading", 8.25, MUTED)))
    for i, (key, label, colour, uw) in enumerate(FUELS):
        x = CARD_X[i]; y = 546; z = 320 + i * 10; f = [fuel_filter(key)]
        # As in the mock-up: the figures quiet, the gap in black on the right; under them
        # two bars, this week and the average (R1, 23 Nov 2026). The label sits 3 px lower
        # to share the gap's baseline.
        V += [
            container(f"p{i}bg", x, y, CARD_W, 66, z, blank(PAPER, border=LINE, radius=8)),
            container(f"p{i}now", x + 14, y + 8, 372, PRESSURE_H, z + 2, pressure_chart("Margin Now Level", ORANGE), f),
            container(f"p{i}avg", x + 14, y + 21, 372, PRESSURE_H, z + 3, pressure_chart("Margin Norm Level", "#F8D2C2"), f),
            container(f"p{i}lbl", x + 16, y + 11, 260, 18, z + 5, title_text("margin_compression", "Cost Pressure Label", 9, MUTED), f),
            container(f"p{i}gap", x + 276, y + 8, 108, 22, z + 6,
                      title_text("margin_compression", "Cost Pressure Gap Label", 11.25, INK, bold=True, align="right"), f),
        ]
    V.append(container("footer", 24, 628, 1112, 40, 400, title_shape("prices", "Now Footer", 8.25, FAINT, bold=False)))
    V += footer_links(1256, 628, [("How it's built", "p4built", 62), (" · ", None, 12), ("Data", "p5data", 24)], 410)
    return V

def page_test():
    V = header()
    slicer = {"visualType": "slicer",
              "query": {"queryState": {"Values": {"projections": [proj("c", "As Of", "As of week", "As of week")]}}},
              "objects": {"data": [obj({"mode": s("Dropdown")})],
                          "selection": [obj({"singleSelect": b(True), "strictSingleSelect": b(True)})]},
              "visualContainerObjects": chrome(title_props={"show": b(True), "text": s("As of week (blank = newest)"),
                                                            "fontSize": d(10)}),
              "drillFilterOtherVisuals": True}
    V.append(container("asof", 24, 64, 300, 64, 100, slicer))
    V.append(container("headline", 340, 58, 916, 90, 101, title_shape("prices", "Headline", 14)))
    table = {"visualType": "tableEx",
             "query": {"queryState": {"Values": {"projections": [
                 proj("c", "Fuel", "Fuel name", "Fuel"),
                 proj("m", "prices", "Latest Week"), proj("m", "prices", "Price Now"), proj("m", "prices", "Price 4 Weeks Ago"),
                 proj("m", "prices", "Change 4w"), proj("m", "prices", "Change 4w %"),
                 proj("m", "margin_compression", "Margin Now"), proj("m", "margin_compression", "Margin Norm Now"),
                 proj("m", "margin_compression", "Margin Gap Now")]}}},
             "visualContainerObjects": chrome(), "drillFilterOtherVisuals": True}
    V.append(container("numbers", 24, 160, 1232, 140, 102, table))
    V.append(container("note", 24, 312, 1232, 60, 103, textbox([[
        ("Hidden in the published report. Pick a week: every measure on Now is computed as if that week were the newest. "
         "Compare the headline with the Python mirror, pbip/build/headline_check.py, for the same week.", 9, MUTED, False)]])))
    return V

def page_tip():
    w, h = TIP_SIZE
    return [container("tipfuel", 10, 7, w - 20, h - 14, 0, title_text("prices", "Tooltip Fuel", 9.75, INK, bold=True))]

write_page(ROOT, "p1now", "Now", page_now(STYLES["A"]))
write_page(ROOT, "p9test", "Headline test", page_test(), hidden=True)
write_page(ROOT, TIP, "Fuel tooltip", page_tip(), hidden=True, size=TIP_SIZE, bg=PAPER,
           extra={"type": "Tooltip", "pageBinding": {"name": "a5f0c3e2b1d84c6f9e7a", "type": "Tooltip"}})
pages = json.loads((ROOT / "pages/pages.json").read_text())
mine = ("p1now", "p1nowa", "p8fonts", "p9test", TIP)  # p1nowa and p8fonts: gone
order = [p for p in pages["pageOrder"] if p not in mine]
pages["pageOrder"] = ["p1now"] + order + ["p9test", TIP]
pages["activePageName"] = "p1now"
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(page_now(STYLES["A"])), "visuals on Now")
