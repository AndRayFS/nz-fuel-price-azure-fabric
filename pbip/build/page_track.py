"""Page 2, Track record, written as PBIR: how far the model's calls missed, against
the benchmark that holds the price where it is, over time and by conditions."""
import sys, json, datetime, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
F = "forecast_accuracy"
MODEL, NAIVE, VOLATILE, EDGE = "#2A78D6", "#A3A29B", "#F1ECE2", "#C9DDF5"
MODEL_SOFT, NAIVE_SOFT = "#BCD5F2", "#DCDBD6"     # the right-hand chart's other horizons: 4 Nov review, too bright
LEFT, RIGHT = (24, 172, 774, 468), (814, 172, 442, 468)

# Where the left chart's plot area falls on the page, for the episode labels above
# it: measured on the service render of 4 Nov 2026 from where the 2015 and 2026
# volatile bands begin.
PLOT_X0, PLOT_X1 = 52, 776
D0, D1 = datetime.date(2013, 8, 2), datetime.date(2026, 10, 23)
EPISODES = [("2015–16 glut", datetime.date(2015, 12, 18)), ("2020 COVID", datetime.date(2020, 4, 24)),
            ("2022 Ukraine", datetime.date(2022, 3, 25)), ("2026 Iran–US", datetime.date(2026, 6, 19))]

def x_at(day):
    return PLOT_X0 + (day - D0).days / (D1 - D0).days * (PLOT_X1 - PLOT_X0)

def miss_chart():
    """Trailing 26-week miss of both methods; full-height columns shade the weeks
    called in volatile crude, an error band fills the gap between the lines."""
    S = lambda m: {"metadata": f"{F}.{m}"}
    M, N, ML, NL, V = "Model 26w (chart)", "No Change 26w (chart)", "Model 26w (last)", "No Change 26w (last)", "Volatile (chart)"
    marker = {"strokeWidth": d(0), "showMarker": b(True), "markerShape": s("circle"), "markerSize": d(4)}
    return {"visualType": "lineClusteredColumnComboChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Week", "week", "Week", active=True)]},
            "Y": {"projections": [proj("m", F, V, "Volatile crude")]},
            "Y2": {"projections": [proj("m", F, M, "Model"), proj("m", F, N, "No change"),
                                   proj("m", F, ML, "Model, latest"), proj("m", F, NL, "No change, latest")]}},
            "sortDefinition": {"sort": [{"field": cref("Week", "week"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            # The column series ignored its own selector and took the theme's first colour,
            # INK; the default fill reaches it, and every line has a selector of its own.
            "dataPoint": [obj({"fill": col(VOLATILE)}), obj({"fill": col(VOLATILE)}, S(V)),
                          obj({"fill": col(MODEL)}, S(M)), obj({"fill": col(NAIVE)}, S(N)),
                          obj({"fill": col(MODEL)}, S(ML)), obj({"fill": col(NAIVE)}, S(NL))],
            "lineStyles": [obj({"strokeWidth": d(2), "showMarker": b(False)}, S(M)),
                           obj({"strokeWidth": d(2), "showMarker": b(False)}, S(N)),
                           obj(dict(marker, markerColor=col(MODEL)), S(ML)), obj(dict(marker, markerColor=col(NAIVE)), S(NL))],
            # Labels on for the chart, then off series by series: a per-series "show" under a
            # chart-wide "off" drew nothing (4 Nov 2026).
            "labels": [obj({"show": b(True), "fontSize": d(9)}),
                       obj({"showSeries": b(False)}, S(V)), obj({"showSeries": b(False)}, S(M)), obj({"showSeries": b(False)}, S(N)),
                       obj({"showSeries": b(True), "color": col(MODEL), "labelPosition": s("Right")}, S(ML)),
                       obj({"showSeries": b(True), "color": col(MUTED), "labelPosition": s("Right")}, S(NL))],
            "error": [obj({"enabled": b(True), "barShow": b(False), "shadeShow": b(True)}, S(M)),
                      obj({"errorRange": {"kind": "ErrorRange", "explicit": {"isRelative": b(False),
                            "upperBound": mexpr(F, N), "lowerBound": mexpr(F, M)}}},
                          {"data": [{"dataViewWildcard": {"matchingOption": 0}}], "metadata": f"{F}.{M}", "highlightMatching": 1})],
            "categoryAxis": [obj({"show": b(True), "axisType": s("Scalar"), "showAxisTitle": b(False), "gridlineShow": b(False),
                                  "fontSize": d(8), "labelColor": col(FAINT), "innerPadding": L(0)})],
            "valueAxis": [obj({"show": b(True), "start": d(0), "showAxisTitle": b(False), "gridlineShow": b(True),
                               "gridlineColor": col("#ECEBE6"), "fontSize": d(8), "labelColor": col(FAINT), "secShow": b(False)})],
            "legend": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def rows_chart(chosen=False):
    """Model and no change side by side, per horizon in calm and volatile crude. Drawn
    twice, one over the other on the same axis: muted for every row, then full colour
    for the chosen horizon's rows only, as the mock-up fades the others."""
    S = lambda m: {"metadata": f"{F}.{m}"}
    M, N = ("Miss Model (row, chosen)", "Miss No Change (row, chosen)") if chosen else ("Miss Model (row)", "Miss No Change (row)")
    fills = (MODEL, NAIVE) if chosen else (MODEL_SOFT, NAIVE_SOFT)
    return {"visualType": "clusteredBarChart",
        "query": {"queryState": {
            "Category": {"projections": [proj("c", "Track Row", "Row", "Row", active=True)]},
            "Y": {"projections": [proj("m", F, M, "Model"), proj("m", F, N, "No change")]}},
            "sortDefinition": {"sort": [{"field": cref("Track Row", "Row"), "direction": "Ascending"}], "isDefaultSort": True}},
        "objects": {
            "dataPoint": [obj({"fill": col(fills[0])}, S(M)), obj({"fill": col(fills[1])}, S(N))],
            "labels": [obj({"show": b(not chosen), "fontSize": d(8), "color": col(MUTED)})],
            "categoryAxis": [obj({"show": b(True), "showAxisTitle": b(False), "fontSize": d(8.25), "labelColor": col(MUTED),
                                  "innerPadding": L(35)})],
            "valueAxis": [obj({"show": b(True), "start": d(0), "end": mexpr(F, "Rows Axis End"), "showAxisTitle": b(False),
                               "gridlineShow": b(not chosen), "gridlineColor": col("#ECEBE6"), "fontSize": d(8),
                               "labelColor": col(FAINT)})],
            "legend": [obj({"show": b(False)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def legend_row(x, y, z):
    """The left chart's key, drawn as shapes like Now's."""
    V = []
    for k, (text, w, h, dy, fill, border, lw) in enumerate([
            ("Model", 16, 2, 6, MODEL, None, 40), ("No change", 16, 2, 6, NAIVE, None, 62),
            ("The model's edge", 12, 10, 2, EDGE, None, 100), ("Volatile crude", 12, 10, 2, VOLATILE, "#E2DCCF", 84)]):
        V.append(container(f"lk{k}", x, y + dy, w, h, z + k, blank(fill, border=border)))
        V.append(container(f"lk{k}t", x + w + 6, y - 3, lw, 20, z + k, textbox([[(text, 9, MUTED, False)]])))
        x += w + 6 + lw + 14
    return V

def page_track():
    V = header()
    z = 100
    V.append(container("headline", 24, 60, 1232, 64, z, title_shape(F, "Track Headline", 17)))
    V.append(container("sub", 24, 134, 640, 36, z + 1, textbox([[(
        "Walk-forward backtest: each week the model is refit on what was known that week, then scored against what followed.",
        9.75, MUTED, False)]])))
    V += [container("fuelbg", 688, 130, 318, 34, z + 2, blank("#EFEEEA", border="#EFEEEA", radius=8)),
          container("fuellbl", 698, 138, 32, 20, z + 3, textbox([[("Fuel", 9, MUTED, False)]])),
          container("fuel", 730, 130, 276, 34, z + 4,
                    button_slicer("Fuel", "Fuel name", "'Regular 91'", 3, grouped=True, accent=(F, "Fuel Accent"))),
          container("hzbg", 1022, 130, 234, 34, z + 5, blank("#EFEEEA", border="#EFEEEA", radius=8)),
          container("hzlbl", 1032, 138, 76, 20, z + 6, textbox([[("Weeks ahead", 9, MUTED, False)]])),
          container("hz", 1108, 130, 148, 34, z + 7, button_slicer("Horizon", "Weeks ahead", "1L", 3, grouped=True, align="center"))]

    x, y, w, h = LEFT; z = 200
    V += [container("lbg", x, y, w, h, z, blank(PAPER, border=LINE, radius=8)),
          container("ltitle", x + 16, y + 12, w - 32, 24, z + 1, title_shape(F, "Track Lead Title", 12)),
          container("lsub", x + 16, y + 38, w - 32, 18, z + 2,
                    textbox([[("Average miss over the trailing 26 weeks, c/L", 9, MUTED, False)]])),
          # The key sits under the subtitle, in the band the data labels' headroom left
          # empty above the plot (4 Nov review); the chart takes the card's full height.
          container("lchart", x + 8, y + 70, w - 16, 386, z + 3, miss_chart())]
    V += legend_row(x + 16, y + 64, z + 10)
    for k, (text, day) in enumerate(EPISODES):
        V.append(container(f"lep{k}", round(x_at(day)) - 45, y + 88, 90, 16, z + 4,
                           textbox([[(text, 8, FAINT, False)]], align="center")))

    x, y, w, h = RIGHT; z = 300
    V += [container("rbg", x, y, w, h, z, blank(PAPER, border=LINE, radius=8)),
          container("rtitle", x + 16, y + 12, w - 32, 46, z + 1, title_shape(F, "Track Regime Title", 12)),
          container("rsub", x + 16, y + 60, w - 32, 18, z + 2,
                    textbox([[("Average miss by weeks ahead, c/L · every call since Feb 2013", 9, MUTED, False)]]))]
    for k, (text, fill, lw) in enumerate([("Model", MODEL, 40), ("No change", NAIVE, 62)]):
        kx = x + 16 + k * 70
        V += [container(f"rk{k}", kx, y + 88, 10, 10, z + 2, blank(fill)),
              container(f"rk{k}t", kx + 16, y + 83, lw, 20, z + 2, textbox([[(text, 9, MUTED, False)]]))]
    # The chosen horizon's two rows get a pale background, as in the mock-up; a box per
    # horizon whose fill comes from a measure, since a shape cannot move with a slicer.
    # Row positions measured on the service render of 4 Nov 2026: the first row starts
    # 16 px into the chart, and each horizon's pair of rows is 80.6 px tall.
    V += [container(f"rhl{n}", x + 8, y + 120 + round((n - 1) * 80.6), w - 16, 81, z + 3, fx_box(F, f"Row Fill {n}"))
          for n in (1, 2, 3)]
    V += [container("rchart", x + 8, y + 104, w - 16, 290, z + 6, rows_chart()),
          container("rchosen", x + 8, y + 104, w - 16, 290, z + 7, rows_chart(chosen=True)),
          container("rnote", x + 16, y + 402, w - 32, 56, z + 7, textbox([[(
              "The chosen horizon is highlighted. Volatile: crude-price volatility above its calm baseline, "
              "about one week in six.", 8.25, MUTED, False)]]))]

    V += footer_links(1256, 652, [("How it's built", "p4built", 62), (" · ", None, 12),
                                  ("Every call and outcome", "p5data", 116)], 410)
    V.append(container("footer", 24, 652, 1022, 40, 400, textbox([[(
        "The record starts in Feb 2013: MBIE's price components add up only from 2010, and the model needs three years "
        "of data before its first call. Scored on today's revised data, which flatters both methods alike.",
        8.25, FAINT, False)]])))
    return V

write_page(ROOT, "p2track", "Track record", page_track())
pages = json.loads((ROOT / "pages/pages.json").read_text())
order = [p for p in pages["pageOrder"] if p != "p2track"]
order.insert(order.index("p1now") + 1, "p2track")
pages["pageOrder"] = order
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(page_track()), "visuals on Track record")
