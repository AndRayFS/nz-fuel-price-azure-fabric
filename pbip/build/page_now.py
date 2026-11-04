"""Page 1, Now, and the hidden headline test page, written as PBIR."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
FUELS = [("Regular Petrol", "Regular 91", "#40B54A", 78),
         ("Premium Petrol 95R", "Premium 95", "#E5C700", 82),
         ("Diesel", "Diesel", "#4D4C48", 46)]
CARD_X = [24, 440, 856]; CARD_W = 400
TRACK = "#ECEBE6"
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

def calls_matrix():
    return {"visualType": "pivotTable",
        "query": {"queryState": {
            "Columns": {"projections": [proj("c", "Week", "Week short", "Week", active=True)]},
            "Values": {"projections": [proj("m", "forecast_accuracy", "Call Number", "Model's call")]}}},
        "objects": {
            "columnHeaders": [obj({"fontColor": col(FAINT), "fontSize": d(8), "fontFamily": wf(FONT), "alignment": s("Left"),
                                   "outlineStyle": L(0), "backColor": col(PAPER)})],
            "values": [obj({"fontColorPrimary": col(CALL), "fontColorSecondary": col(CALL), "fontSize": d(11),
                            "fontFamily": wf(FONT_B), "outlineStyle": L(0),
                            "backColorPrimary": col(PAPER), "backColorSecondary": col(PAPER)})],
            "grid": [obj({"gridVertical": b(False), "gridHorizontal": b(False), "outlineColor": col(PAPER), "rowPadding": d(2)})],
            "subTotals": [obj({"columnSubtotals": b(False), "rowSubtotals": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def pressure_chart(measure, bar):
    """One bar on a 0-60 c/L axis. The track and the margin are two of these, one over
    the other: in a single stacked chart Power BI dropped both the colour measure and
    the norm's error-bar tick (4 Nov 2026), and both work on a single series."""
    ref = "margin_compression." + measure
    v = {"visualType": "barChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Fuel", "Fuel name", "Fuel", active=True)]},
            "Y": {"projections": [proj("m", "margin_compression", measure, measure)]}}},
        "objects": {
            "dataPoint": [obj({"fill": mcol("margin_compression", "Cost Pressure Colour")},
                              {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}) if bar else obj({"fill": col(TRACK)})],
            "valueAxis": [obj({"show": b(False), "start": d(0), "end": d(60), "gridlineShow": b(False)})],
            "categoryAxis": [obj({"show": b(False), "showAxisTitle": b(False), "innerPadding": L(55)})],
            "legend": [obj({"show": b(False)})],
            "labels": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    if bar:
        v["objects"]["error"] = [
            obj({"enabled": b(True), "barShow": b(True), "shadeShow": b(False), "barColor": col(INK),
                 "barWidth": d(14), "barBorderSize": L(0)}, {"metadata": ref}),
            obj({"errorRange": {"kind": "ErrorRange", "explicit": {
                    "isRelative": b(False),
                    "upperBound": mexpr("margin_compression", "Margin Norm Bar"),
                    "lowerBound": mexpr("margin_compression", "Margin Norm Bar")}}},
                {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": ref, "highlightMatching": 1})]
    return v

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

def page_fonts():
    """Four type treatments of the same live numbers, side by side, to choose from."""
    V = header()
    variants = [
        ("A", "Segoe UI, as now", dict(head="Segoe UI Semibold", num="Segoe UI Semibold", text="Segoe UI")),
        ("B", "Segoe UI Light for large type", dict(head="Segoe UI Light", num="Segoe UI Light", text="Segoe UI")),
        ("C", "DIN for figures, Segoe UI for words", dict(head="Segoe UI Semibold", num="DIN", text="Segoe UI")),
        ("D", "Georgia headline, editorial", dict(head="Georgia", num="Segoe UI Semibold", text="Segoe UI")),
    ]
    f = [fuel_filter("Regular Petrol")]
    for k, (tag, name, fc) in enumerate(variants):
        x = 24 + k * 312; z = 100 + k * 20
        V += [
            container(f"f{tag}bg", x, 64, 296, 600, z, blank(PAPER, border=LINE, radius=8)),
            container(f"f{tag}name", x + 14, 72, 268, 20, z + 1, textbox([[(f"{tag}. {name}", 9, MUTED, False)]])),
            container(f"f{tag}head", x + 14, 98, 268, 150, z + 2, title_shape("prices", "Headline", 15, face=fc["head"])),
            container(f"f{tag}num", x + 14, 262, 120, 40, z + 3, title_text("prices", "Price Now Number", 21, INK, face=fc["num"]), f),
            container(f"f{tag}chg", x + 14, 310, 268, 20, z + 4, title_text("prices", "Change 4w Main", 9, INK, face=fc["num"]), f),
            container(f"f{tag}wk", x + 14, 340, 268, 18, z + 5, title_text("prices", "Week To Label", 8.25, MUTED, face=fc["text"])),
        ] + [c for n in (1, 2, 3) for c in (
            container(f"f{tag}d{n}", x + 14 + (n - 1) * 88, 372, 86, 18, z + 6,
                      title_text("forecast_accuracy", f"Call Date {n}", 8.25, FAINT, face=fc["text"]), f),
            container(f"f{tag}v{n}", x + 14 + (n - 1) * 88, 390, 86, 28, z + 7,
                      title_text("forecast_accuracy", f"Call {n}", 11.25, CALL, face=fc["num"]), f))] + [
            container(f"f{tag}foot", x + 14, 440, 268, 120, z + 8, title_shape("prices", "Now Footer", 8.25, FAINT, face=fc["text"])),
        ]
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
            container(f"c{i}bg", x, 172, CARD_W, 352, z, blank(PAPER, border=LINE, radius=8)),
            container(f"c{i}name", x + 14, 178, 220, 24, z + 1, textbox([[(label, 11, INK, True)]])),
            container(f"c{i}uline", x + 16, 203, uw, 3, z + 2, blank(colour)),
            container(f"c{i}weekto", x + 16, 212, 368, 18, z + 3, title_text("prices", "Week To Label", 8.25, MUTED)),
            container(f"c{i}price", x + 16, 230, 96, 38, z + 4, title_text("prices", "Price Now Number", 21, INK, face=style["num"]), f),
            container(f"c{i}unit", x + 92, 244, 40, 20, z + 4, textbox([[("c/L", 9.75, MUTED, False)]])),
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
    V.append(container("cphead", 24, 532, 130, 22, z, textbox([[("Cost pressure", 10.5, INK, True)]])))
    V.append(container("cpnote", 152, 535, 1104, 18, z + 1, title_text("margin_compression", "Cost Pressure Heading", 8.25, MUTED)))
    for i, (key, label, colour, uw) in enumerate(FUELS):
        x = CARD_X[i]; y = 556; z = 320 + i * 10; f = [fuel_filter(key)]
        # As in the mock-up: the figures quiet, the gap in black on the right, then an
        # 8 px track with the norm's tick. The label sits 3 px lower to share the gap's baseline.
        V += [
            container(f"p{i}bg", x, y, CARD_W, 54, z, blank(PAPER, border=LINE, radius=8)),
            container(f"p{i}track", x + 14, y + 10, 372, 56, z + 1, pressure_chart("Track Full", bar=False), f),
            container(f"p{i}bar", x + 14, y + 10, 372, 56, z + 2, pressure_chart("Margin Bar", bar=True), f),
            container(f"p{i}lbl", x + 16, y + 11, 260, 18, z + 5, title_text("margin_compression", "Cost Pressure Label", 9, MUTED), f),
            container(f"p{i}gap", x + 276, y + 8, 108, 22, z + 6,
                      title_text("margin_compression", "Cost Pressure Gap Label", 11.25, INK, bold=True, align="right"), f),
        ]
    V.append(container("footer", 24, 628, 1232, 40, 400, title_shape("prices", "Now Footer", 8.25, FAINT, bold=False)))
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

write_page(ROOT, "p1now", "Now", page_now(STYLES["A"]))
write_page(ROOT, "p9test", "Headline test", page_test(), hidden=True)
write_page(ROOT, "p8fonts", "Fonts", page_fonts(), hidden=True)
pages = json.loads((ROOT / "pages/pages.json").read_text())
mine = ("p1now", "p1nowa", "p8fonts", "p9test")  # p1nowa: the A/B copy, gone
order = [p for p in pages["pageOrder"] if p not in mine]
pages["pageOrder"] = ["p1now"] + order + ["p8fonts", "p9test"]
pages["activePageName"] = "p1now"
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(page_now(STYLES["A"])), "visuals on Now")
