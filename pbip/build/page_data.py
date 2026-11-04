"""Page 5, Data, written as PBIR: every number behind the report, one table at a time
- the calls and their outcomes, the margin, the weekly prices - and the archive link.

The three tables share one page and one fuel selector. Three bookmarks switch between
them: each shows its own table, caption, glossary and the white segment under its
button, and hides the other two sets. The bookmarks carry display state only
(suppressData), so the fuel and horizon chosen survive the switch."""
import sys, json, pathlib, shutil
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
F, M, P = "forecast_accuracy", "margin_compression", "prices"
PAGE = "p5data"
PILL, ROW_LINE, HEAD_LINE = "#EFEEEA", "#ECEBE6", "#C9C8C1"
ZIP = "https://nzfueldata.blob.core.windows.net/data/latest/nz-fuel-latest.zip"
BM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json"
BM_META = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json"

CARD = (24, 172, 860, 470)             # the table's card
SIDE = (900, 172, 356)                  # the right-hand column: x, y, width

# (key, button label, segment x, segment width, bookmark, caption measure, columns, glossary)
# columns: (field kind, entity, name, header, width, right-aligned, colour measure)
VIEWS = [
    ("calls", "Calls and outcomes", 27, 146, "bmCalls", (F, "Data Calls Caption"), [
        ("c", F, "week_date", "Call made", 108, False, None),
        ("c", F, "Target week", "For week", 108, False, None),
        ("m", F, "Data Price Then", "Price then", 96, True, None),
        ("m", F, "Data Model Call", "Model's call", 106, True, None),
        ("m", F, "Data Actual", "Actual", 90, True, None),
        ("m", F, "Data Model Miss", "Model missed by", 136, True, "Data Model Miss Colour"),
        ("m", F, "Data No Change Miss", "“No change” missed by", 160, True, "Data No Change Miss Colour")], [
        ("Call made", "the week the model made its call, using only the data of that week."),
        ("Model's call", "the price it indicated for the week the call was for."),
        ("“No change”", "the benchmark: the price stays where it was, so its call is the price then."),
        ("Missed by", "how far a call sat from the price that followed, in cents per litre.")]),
    ("margin", "Margin", 173, 84, "bmMargin", (M, "Data Margin Caption"), [
        ("c", M, "week_date", "Week", 104, False, None),
        ("m", M, "Data Margin", "Margin", 80, True, None),
        ("m", M, "Data Norm", "Two-year average", 116, True, None),
        ("m", M, "Gap (chart)", "Gap", 70, True, None),
        ("m", M, "Data Margin Before Adjustment", "Margin before MBIE's adjustment", 130, True, None),
        ("m", M, "Gap Before Adjustment (chart)", "Gap before adjustment", 120, True, None),
        ("m", M, "Data Margin Status", "Status", 180, False, None)], [
        ("Margin", "what is left of the pump price after taxes, GST, ETS and MBIE's estimate of the importer's cost."),
        ("Two-year average", "the margin's average over the 104 weeks before."),
        ("Gap", "the margin less its two-year average."),
        ("Before MBIE's adjustment", "from 27 Feb 2026 MBIE adds to the cost what the Commerce Commission found importers "
                                     "paid above the benchmarks; these columns leave it out. Split published to 11 Sep."),
        ("Filled in later", "weeks MBIE suspended and published afterwards.")]),
    ("prices", "Weekly prices since 2004", 257, 176, "bmPrices", (P, "Data Prices Caption"), [
        ("c", P, "week_date", "Week", 120, False, None),
        ("m", P, "Data Pump Price", "Pump price", 114, True, None),
        ("m", P, "Data Importer Cost", "Importer cost", 114, True, None),
        ("m", P, "Data Taxes", "Taxes and levies", 114, True, None),
        ("m", P, "Data ETS", "ETS", 114, True, None),
        ("m", P, "Data GST", "GST", 114, True, None),
        ("m", P, "Data Importer Margin", "Importer margin", 114, True, None)], [
        ("Pump price", "MBIE's adjusted retail price for the week."),
        ("Importer cost", "MBIE's estimate of what a litre cost to land in New Zealand."),
        ("Taxes and levies", "excise and the other levies; diesel's road taxes are paid as road user charges instead."),
        ("ETS", "the emissions trading cost."),
        ("Importer margin", "what is left: the price less the four parts before it.")]),
]

def table(cols, entity):
    """A plain table: no totals, no vertical grid, thin rules between rows, newest week first."""
    ref = lambda kind, ent, name: f"{ent}.{name}"
    date = cref(cols[0][1], cols[0][2])
    objects = {
        "grid": [obj({"gridVertical": b(False), "gridHorizontal": b(True), "gridHorizontalColor": col(ROW_LINE),
                      "gridHorizontalWeight": d(1), "rowPadding": d(4), "outlineColor": col(HEAD_LINE), "outlineWeight": d(1)})],
        "columnHeaders": [obj({"fontColor": col(MUTED), "backColor": col(PAPER), "fontSize": d(9), "fontFamily": wf(FONT),
                               "outline": s("BottomOnly"), "wordWrap": b(True), "autoSizeColumnWidth": b(False)})],
        "values": [obj({"fontColorPrimary": col(INK), "backColorPrimary": col(PAPER), "fontColorSecondary": col(INK),
                        "backColorSecondary": col(PAPER), "fontSize": d(9.75), "fontFamily": wf(FONT),
                        "outline": s("None"), "wordWrap": b(False)})],
        "total": [obj({"totals": b(False)})],
        "columnWidth": [obj({"value": d(w)}, {"metadata": ref(k, e, n)}) for k, e, n, _, w, _, _ in cols],
        # Header and values aligned together: numbers right, dates and text left. With the
        # values alone right-aligned, a left header sat between two columns (4 Nov review).
        "columnFormatting": [obj({"alignment": s("Right" if right else "Left"), "styleHeader": b(True), "styleValues": b(True)},
                                 {"metadata": ref(k, e, n)}) for k, e, n, _, _, right, _ in cols],
    }
    objects["values"] += [obj({"fontColor": mcol(F, cm)}, {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                                                           "metadata": ref(k, e, n)})
                          for k, e, n, _, _, _, cm in cols if cm]
    return {"visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": [proj(k, e, n, h) for k, e, n, h, _, _, _ in cols]}},
                  "sortDefinition": {"sort": [{"field": date, "direction": "Descending"}]}},
        "objects": objects,
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}

def glossary(entries):
    paras = [[(term, 9, INK, True), (" — " + text, 9, MUTED, False)] for term, text in entries]
    v = textbox(paras)
    for p in v["objects"]["general"][0]["properties"]["paragraphs"]:
        p["textRuns"][0]["textStyle"]["fontFamily"] = FONT_B
    return v

def button(link, tip):
    """A transparent button over a label: link is ("Bookmark", name) or ("WebUrl", url)."""
    kind, target = link
    off = {"show": b(False)}
    # Off with and without a selector, in every state: with "default" alone the service
    # still drew a dark 2 px border round each button (4 Nov 2026).
    states = [None] + [{"id": st} for st in ("default", "hover", "press", "selected")]
    no_fill = {"show": b(False), "fillColor": col(PAPER), "transparency": d(100)}
    no_line = {"show": b(False), "lineColor": col(PAPER), "transparency": d(100), "weight": d(0)}
    vl = {"show": b(True), "type": s(kind), "tooltip": s(tip)}
    vl["bookmark" if kind == "Bookmark" else "webUrl"] = s(target)
    v = {"visualType": "actionButton",
         "objects": {"icon": [obj(off, st) for st in states], "text": [obj(off, st) for st in states],
                     "fill": [obj(no_fill, st) for st in states], "outline": [obj(no_line, st) for st in states]},
         "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    v["visualContainerObjects"]["visualLink"] = [obj(vl)]
    return v

def page_data():
    V = header()
    V += [container("title", 24, 60, 1232, 32, 100, textbox([[("Every number in this report, week by week", 17, INK, True)]])),
          container("sub", 24, 94, 1232, 22, 101, textbox([[(
              "MBIE revises past weeks, so every weekly load is also kept as a dated copy you can download.", 10.5, MUTED, False)]]))]

    # The view switch: a grey pill, the labels, a white segment under the chosen one, buttons on top.
    toggled = {key: [] for key, *_ in VIEWS}
    V.append(container("vpill", 24, 124, 412, 34, 150, blank(PILL, border=PILL, radius=8)))
    for i, (key, label, sx, sw, bm, *_r) in enumerate(VIEWS):
        hidden = i > 0
        V += [container(f"v{key}lab", sx, 132, sw, 20, 151, textbox([[(label, 9, MUTED, False)]], align="center")),
              container(f"v{key}seg", sx, 127, sw, 28, 160, blank(PAPER, border=PAPER, radius=6), hidden=hidden),
              container(f"v{key}on", sx, 132, sw, 20, 161, textbox([[(label, 9, INK, True)]], align="center"), hidden=hidden),
              container(f"v{key}btn", sx, 127, sw, 28, 170, button(("Bookmark", bm), "Show " + label.lower()))]
        toggled[key] += [f"v{key}seg", f"v{key}on"]

    z = 180
    V += [container("fuelbg", 688, 124, 318, 34, z, blank(PILL, border=PILL, radius=8)),
          container("fuellbl", 698, 132, 32, 20, z + 1, textbox([[("Fuel", 9, MUTED, False)]])),
          container("fuel", 730, 124, 276, 34, z + 2,
                    button_slicer("Fuel", "Fuel name", "'Regular 91'", 3, grouped=True, accent=(F, "Fuel Accent"))),
          container("hzbg", 1022, 124, 234, 34, z + 3, blank(PILL, border=PILL, radius=8)),
          container("hzlbl", 1032, 132, 76, 20, z + 4, textbox([[("Weeks ahead", 9, MUTED, False)]])),
          container("hz", 1108, 124, 148, 34, z + 5, button_slicer("Horizon", "Weeks ahead", "1L", 3, grouped=True, align="center"))]
    toggled["calls"] += ["hzbg", "hzlbl", "hz"]

    x, y, w, h = CARD
    V.append(container("tcard", x, y, w, h, 200, blank(PAPER, border=LINE, radius=8)))
    for i, (key, label, sx, sw, bm, cap, cols, gloss) in enumerate(VIEWS):
        hidden = i > 0
        V += [container(f"t{key}", x + 16, y + 8, w - 32, h - 44, 210 + i, table(cols, cols[0][1]), hidden=hidden),
              container(f"c{key}", x + 22, y + h - 30, w - 44, 18, 220 + i, title_text(*cap, 8.25, FAINT), hidden=hidden)]
        toggled[key] += [f"t{key}", f"c{key}"]

    sx, sy, sw = SIDE
    V += [container("dcard", sx, sy, sw, 140, 300, blank(PAPER, border=LINE, radius=8)),
          container("dtitle", sx + 16, sy + 12, sw - 32, 24, 301, textbox([[("Download all of it", 12, INK, True)]])),
          container("dbtn", sx + 16, sy + 42, sw - 32, 50, 302, blank(INK, border=INK, radius=8)),
          container("dbtnt", sx + 30, sy + 48, sw - 60, 40, 303, textbox([
              [("nz-fuel-latest.zip", 10.5, PAPER, True)], [("three CSV tables and a README", 9, HEAD_LINE, False)]])),
          container("dbtnl", sx + 16, sy + 42, sw - 32, 50, 304, button(("WebUrl", ZIP), "Download nz-fuel-latest.zip")),
          container("dnote", sx + 16, sy + 100, sw - 32, 32, 305, textbox([[(
              "Each week's load is also kept under its own date, as it was published.", 8.25, MUTED, False)]]))]
    gy = sy + 152
    V += [container("gcard", sx, gy, sw, CARD[1] + CARD[3] - gy, 310, blank(PAPER, border=LINE, radius=8)),
          container("gtitle", sx + 16, gy + 12, sw - 32, 24, 311, textbox([[("What the columns mean", 12, INK, True)]]))]
    for i, (key, *_r, gloss) in enumerate(VIEWS):
        V.append(container(f"g{key}", sx + 16, gy + 44, sw - 32, CARD[1] + CARD[3] - gy - 56, 320 + i, glossary(gloss),
                           hidden=i > 0))
        toggled[key].append(f"g{key}")

    V.append(container("footer", 24, 662, 1232, 30, 400, textbox([[(
        "Source: MBIE weekly fuel price monitoring (CC BY 4.0). Calls, misses, norms and gaps are this project's "
        "calculations on MBIE's data.", 8.25, FAINT, False)]])))
    return V, toggled

def bookmarks(visuals, toggled):
    """One bookmark per view: its own set shown, the other two hidden, nothing else touched."""
    vtype = {v["name"]: v["visual"]["visualType"] for v in visuals}
    targets = [n for names in toggled.values() for n in names]
    bdir = ROOT / "bookmarks"
    if bdir.exists(): shutil.rmtree(bdir)
    bdir.mkdir()
    items = []
    for key, label, _x, _w, bm, *_r in VIEWS:
        state = {}
        for n in targets:
            sv = {"visualType": vtype[n]}
            if n not in toggled[key]: sv["display"] = {"mode": "hidden"}
            state[n] = {"singleVisual": sv}
        doc = {"$schema": BM_SCHEMA, "displayName": label, "name": bm,
               "options": {"applyOnlyToTargetVisuals": True, "targetVisualNames": targets, "suppressData": True},
               "explorationState": {"version": "1.3", "activeSection": PAGE,
                                    "sections": {PAGE: {"visualContainers": state}}}}
        (bdir / f"{bm}.bookmark.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        items.append({"name": bm})
    (bdir / "bookmarks.json").write_text(json.dumps({"$schema": BM_META, "items": items}, indent=2) + "\n")

visuals, toggled = page_data()
write_page(ROOT, PAGE, "Data", visuals)
bookmarks(visuals, toggled)
pages = json.loads((ROOT / "pages/pages.json").read_text())
order = [p for p in pages["pageOrder"] if p != PAGE]
order.insert(order.index("p4built") + 1, PAGE)
pages["pageOrder"] = order
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(visuals), "visuals on Data;", {k: len(v) for k, v in toggled.items()}, "toggled")
