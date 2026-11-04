"""Small builders for PBIR JSON, so pages are written as code and rewritten whole."""
import json, pathlib, shutil

VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.11.0/schema.json"
PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

INK, MUTED, FAINT, LINE, PAPER, BG = "#1B1B19", "#5C5B56", "#8A8983", "#E6E5E0", "#FFFFFF", "#F7F7F5"
CALL, CALL_LINE, ORANGE = "#256ABF", "#2A78D6", "#EB6834"
FONT, FONT_B = "Segoe UI", "Segoe UI Semibold"
# How Power BI itself writes font families into visual properties: the face, then
# the web font it ships with the service, then generic fallbacks. A bare name only
# renders where the viewer has the font installed. Text box runs take bare names.
WEBFONT = {
    "Segoe UI": "'Segoe UI', wf_segoe-ui_normal, helvetica, arial, sans-serif",
    "Segoe UI Semibold": "'Segoe UI Semibold', wf_segoe-ui_semibold, helvetica, arial, sans-serif",
    "Segoe UI Light": "'Segoe UI Light', wf_segoe-ui_light, helvetica, arial, sans-serif",
    "DIN": "wf_standard-font, helvetica, arial, sans-serif",
    "Georgia": "Georgia, 'Times New Roman', serif",
}
def wf(face): return s(WEBFONT[face])

def lit(v): return {"expr": {"Literal": {"Value": v}}}
def s(t): return lit("'" + str(t).replace("'", "''") + "'")
def b(x): return lit("true" if x else "false")
def d(x): return lit(f"{x}D")
def L(x): return lit(f"{int(x)}L")
def col(hexc): return {"solid": {"color": s(hexc)}}
def mref(entity, name): return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": name}}
def cref(entity, name): return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": name}}
def mcol(entity, name): return {"solid": {"color": {"expr": mref(entity, name)}}}
def mexpr(entity, name): return {"expr": mref(entity, name)}
def obj(props, selector=None):
    o = {"properties": props}
    if selector is not None: o["selector"] = selector
    return o
DEFAULT = {"id": "default"}
EACH = {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "id": "default"}

def proj(field, entity, name, display=None, active=None):
    kind = "Measure" if field == "m" else "Column"
    p = {"field": mref(entity, name) if field == "m" else cref(entity, name),
         "queryRef": f"{entity}.{name}", "nativeQueryRef": display or name}
    if display: p["displayName"] = display
    if active is not None: p["active"] = active
    return p

def chrome(title=None, background=None, border=None, radius=None, padding=None, title_props=None):
    """visualContainerObjects shared by every visual: no header, optional title,
    background and border used as the card shapes of the mock-up."""
    v = {"visualHeader": [obj({"show": b(False)})],
         "dropShadow": [obj({"show": b(False)})]}
    if title_props:
        v["title"] = [obj(title_props)]
    else:
        v["title"] = [obj({"show": b(False)})]
    if background:
        v["background"] = [obj({"show": b(True), "color": col(background), "transparency": d(0)})]
    else:
        v["background"] = [obj({"show": b(False)})]
    if border:
        bp = {"show": b(True), "color": col(border)}
        if radius is not None: bp["radius"] = d(radius)
        v["border"] = [obj(bp)]
    else:
        v["border"] = [obj({"show": b(False)})]
    if padding is not None:
        v["padding"] = [obj({k: d(padding[i]) for i, k in enumerate(("top", "bottom", "left", "right"))})]
    return v

def container(name, x, y, w, h, z, visual, filters=None, hidden=False):
    c = {"$schema": VC, "name": name,
         "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
         "visual": visual}
    if filters: c["filterConfig"] = {"filters": filters}
    if hidden: c["isHidden"] = True
    return c

def fuel_filter(fuel_key):
    return {"name": "fuel", "field": cref("Fuel", "fuel"), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "f", "Entity": "Fuel", "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "f"}}, "Property": "fuel"}}],
                           "Values": [[{"Literal": {"Value": "'" + fuel_key + "'"}}]]}}}]},
            "howCreated": "User"}

def measure_is_one(entity, name, fname):
    return {"name": fname, "field": mref(entity, name), "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "x", "Entity": entity, "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {"ComparisonKind": 0,
                           "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "x"}}, "Property": name}},
                           "Right": {"Literal": {"Value": "1L"}}}}}]},
            "howCreated": "User"}

# ---------------------------------------------------------------- visuals
def textbox(runs, align="left", **chrome_kw):
    """runs: list of paragraphs, each a list of (text, size_pt, colour, bold)."""
    paras = []
    for para in runs:
        tr = [{"value": t, "textStyle": {"fontFamily": FONT_B if bold else FONT, "fontSize": f"{size}pt", "color": c}}
              for t, size, c, bold in para]
        p = {"textRuns": tr}
        if align != "left": p["horizontalTextAlignment"] = align
        paras.append(p)
    return {"visualType": "textbox",
            "objects": {"general": [obj({"paragraphs": paras})]},
            "visualContainerObjects": chrome(padding=(0, 0, 0, 0), **chrome_kw),
            "drillFilterOtherVisuals": True}

def blank(background, border=None, radius=None):
    """An empty shape whose container draws a rectangle: card backgrounds, rules, fuel
    underlines, legend marks. It was an empty text box until 4 Nov 2026, but a text box
    under ~16 px high overflows, and Desktop drew its scroll bar as a grey stub at the
    right end of every underline and over the legend's ring and square."""
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(background=background, border=border, radius=radius, padding=(0, 0, 0, 0))
    return v

def text_card(entity, measure, size, colour=INK, bold=False, align="left", colour_measure=None,
              fill_measure=None, radius=0, wrap=False):
    """A new card showing one text measure as plain text: no label, no outline."""
    value = {"fontSize": d(size), "fontFamily": s(FONT_B if bold else FONT),
             "fontColor": mcol(*colour_measure) if colour_measure else col(colour),
             "horizontalAlignment": s(align)}
    if wrap: value["textWrap"] = b(True)
    area = {"show": b(bool(fill_measure))}
    if fill_measure:
        area.update({"backgroundFillColor": mcol(*fill_measure), "backgroundTransparency": d(0),
                     "rectangleRoundedCurve": L(radius)})
    return {"visualType": "cardVisual",
            "query": {"queryState": {"Data": {"projections": [proj("m", entity, measure)]}}},
            "objects": {
                "layout": [obj({"autoGrid": b(True), "cellPadding": L(0), "alignment": s("middle")}, DEFAULT)],
                "value": [obj(value, DEFAULT)],
                "label": [obj({"show": b(False)}, DEFAULT)],
                "outline": [obj({"show": b(False)}, DEFAULT)],
                "accentBar": [obj({"show": b(False)}, DEFAULT)],
                "shadowCustom": [obj({"show": b(False)}, DEFAULT)],
                "padding": [obj({"paddingIndividual": b(False), "paddingUniform": d(4 if fill_measure else 0)}, DEFAULT)],
                "cardCalloutArea": [obj(area, DEFAULT)],
            },
            "visualContainerObjects": chrome(padding=(0, 0, 0, 0)),
            "drillFilterOtherVisuals": True}

def title_shape(entity, measure, size, colour=INK, bold=True, face=None):
    """Long dynamic text: the title of an invisible shape, because a title wraps and a card value may not."""
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0), title_props={
                "show": b(True), "text": mexpr(entity, measure), "titleWrap": b(True),
                "fontSize": d(size), "fontFamily": wf(face or (FONT_B if bold else FONT)), "fontColor": col(colour),
                "alignment": s("left"), "heading": s("Heading1" if size >= 16 else "Normal")})
    return v

def write_page(root, name, display, visuals, hidden=False):
    pdir = pathlib.Path(root) / "pages" / name
    if pdir.exists(): shutil.rmtree(pdir)
    (pdir / "visuals").mkdir(parents=True)
    page = {"$schema": PAGE, "name": name, "displayName": display, "displayOption": "FitToPage",
            "height": 720, "width": 1280,
            "objects": {"background": [obj({"color": col(BG), "transparency": d(0)})],
                        "outspace": [obj({"color": col(BG), "transparency": d(0)})]}}
    if hidden: page["visibility"] = "HiddenInViewMode"
    (pdir / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False) + "\n")
    for v in visuals:
        vd = pdir / "visuals" / v["name"]; vd.mkdir()
        (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n")
    return pdir

def title_text(entity, measure, size, colour=INK, bold=False, align="left", colour_measure=None,
               background_measure=None, radius=None, face=None):
    """Short dynamic text, drawn as the title of an invisible shape. A new card does
    not draw its value in a container under ~30 px high (seen 4 Nov 2026); a title
    renders at any height and wraps."""
    tp = {"show": b(True), "text": mexpr(entity, measure), "titleWrap": b(True),
          "fontSize": d(size), "fontFamily": wf(face or (FONT_B if bold else FONT)),
          "fontColor": mcol(*colour_measure) if colour_measure else col(colour),
          "alignment": s(align), "heading": s("Normal")}
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0), title_props=tp)
    if background_measure:
        v["visualContainerObjects"]["background"] = [obj({"show": b(True), "color": mcol(*background_measure),
                                                          "transparency": d(0)})]
        v["visualContainerObjects"]["border"] = [obj({"show": b(True), "color": col(PAPER), "radius": d(radius or 0)})]
    return v

def title_label(text, size, colour=INK, bold=False, align="left", face=None):
    """Fixed text drawn like title_text, so it shares a baseline with the measures beside it."""
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0), title_props={
        "show": b(True), "text": s(text), "titleWrap": b(False), "fontSize": d(size),
        "fontFamily": wf(face or (FONT_B if bold else FONT)), "fontColor": col(colour),
        "alignment": s(align), "heading": s("Normal")})
    return v

def invisible_shape():
    """A shape with neither fill nor outline. Both switched off twice over - with and
    without a selector, and at full transparency - because the first attempt, with
    show=false alone, still painted the theme's first colour under the title."""
    none_fill = {"show": b(False), "fillColor": col(BG), "transparency": d(100)}
    none_line = {"show": b(False), "lineColor": col(BG), "transparency": d(100)}
    return {"visualType": "shape",
            "objects": {"shape": [obj({"tileShape": s("rectangle")})],
                        "fill": [obj(none_fill), obj(none_fill, DEFAULT)],
                        "outline": [obj(none_line), obj(none_line, DEFAULT)]},
            "drillFilterOtherVisuals": True}


def fx_box(entity, measure, radius=6):
    """A rectangle whose fill comes from a measure: the pill behind the four-week change."""
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0))
    v["visualContainerObjects"]["background"] = [obj({"show": b(True), "color": mcol(entity, measure), "transparency": d(0)})]
    v["visualContainerObjects"]["border"] = [obj({"show": b(True), "color": col(PAPER), "radius": d(radius)})]
    return v


# ---------------------------------------------------------------- shared by the pages
def header(z=0):
    nav = {"visualType": "pageNavigator",
           "objects": {"fill": [obj({"show": b(False), "fillColor": col(PAPER), "transparency": d(100)}, DEFAULT),
                                obj({"show": b(False), "fillColor": col(PAPER), "transparency": d(100)}, {"id": "selected"})],
                       "text": [obj({"fontColor": col(MUTED), "fontSize": d(9.75), "fontFamily": wf(FONT)}, DEFAULT),
                                obj({"fontColor": col(INK), "fontSize": d(9.75), "fontFamily": wf(FONT_B)}, {"id": "selected"})],
                       "accentBar": [obj({"show": b(False)}, DEFAULT),
                                     obj({"show": b(True), "position": s("Bottom"), "width": d(2), "color": col(INK)}, {"id": "selected"})],
                       "outline": [obj({"show": b(False), "lineColor": col(PAPER), "transparency": d(100)}, DEFAULT),
                                   obj({"show": b(False), "lineColor": col("#EFEEEA"), "transparency": d(100)}, {"id": "selected"})],
                       "pages": [obj({"showHiddenPages": b(False)})]},
           "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    return [
        container("hdrbg", 0, 0, 1280, 48, z, blank(PAPER)),
        container("hdrrule", 0, 48, 1280, 1, z + 1, blank(LINE)),
        container("hdrbrand", 24, 14, 240, 24, z + 2, textbox([[("NZ fuel prices · oil to pump", 10.5, INK, True)]])),
        container("hdrnav", 272, 6, 520, 36, z + 3, nav),
        container("hdrweeks", 880, 17, 376, 24, z + 4, title_text("prices", "Header Weeks", 9, MUTED, align="right")),
    ]

def button_slicer(entity, column, default, columns, grouped=False, align=None, accent=None):
    """One button per value of a column, one always selected. grouped=True leaves the grey
    pill to a shape behind, so a label can sit inside it with the buttons. accent=(entity,
    measure) draws a bar under each button in the colour the measure gives for its value."""
    each = lambda state: {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "id": state, "hierarchyMatching": 1}
    value = {"textWrap": b(False), "fontSize": d(9), "fontColor": col(MUTED), "fontFamily": wf(FONT)}
    if align: value["horizontalAlignment"] = s(align)
    bar = [obj({"show": b(False)}, DEFAULT)]
    if accent:
        bar = [obj({"show": b(True), "position": s("Bottom"), "width": d(2)}, DEFAULT),
               obj({"show": b(True)}, {"id": "selection:selected"}),
               obj({"color": mcol(*accent)}, each("default")), obj({"color": mcol(*accent)}, each("selection:selected"))]
    return {"visualType": "advancedSlicerVisual",
        "query": {"queryState": {"Values": {"projections": [proj("c", entity, column, column)]}},
                  "sortDefinition": {"sort": [{"field": cref(entity, column), "direction": "Ascending"}]}},
        "objects": {
            "selection": [obj({"singleSelect": b(True), "strictSingleSelect": b(True)})],
            "general": [obj({"filter": {"filter": {"Version": 2,
                "From": [{"Name": "p", "Entity": entity, "Type": 0}],
                "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "p"}}, "Property": column}}],
                                                "Values": [[{"Literal": {"Value": default}}]]}}}]}}})],
            "fillCustom": [obj({"show": b(True), "fillColor": col("#EFEEEA"), "transparency": d(0)}, DEFAULT),
                           obj({"fillColor": col(PAPER), "transparency": d(0)}, {"id": "selection:selected"})],
            "value": [obj({"show": b(True)}),
                      obj(value, DEFAULT),
                      obj({"fontColor": col(INK), "fontFamily": wf(FONT_B)}, {"id": "selection:selected"})],
            "label": [obj({"show": b(False)}, DEFAULT)],
            "outline": [obj({"show": b(False)}, DEFAULT)],
            "accentBar": bar,
            "selectionIcon": [obj({"show": b(False)})],
            "shapeCustomRectangle": [obj({"rectangleRoundedCurve": L(6)}, DEFAULT)],
            "padding": [obj({"paddingSelection": s("Narrow")}, DEFAULT)],
            "layout": [obj({"showFixedSize": b(False), "autoGrid": b(False), "rowCount": L(1), "columnCount": L(columns)})],
        },
        "visualContainerObjects": chrome(padding=(0, 0, 0, 0)) if grouped else
            chrome(padding=(0, 0, 0, 0), background="#EFEEEA", border="#EFEEEA", radius=8),
        "drillFilterOtherVisuals": True}

def link_button(link, tip):
    """A transparent button over a label: link is ("Bookmark", name), ("WebUrl", url) or
    ("PageNavigation", page name)."""
    kind, target = link
    off = {"show": b(False)}
    # Off with and without a selector, in every state: with "default" alone the service
    # still drew a dark 2 px border round each button (4 Nov 2026).
    states = [None] + [{"id": st} for st in ("default", "hover", "press", "selected")]
    no_fill = {"show": b(False), "fillColor": col(PAPER), "transparency": d(100)}
    no_line = {"show": b(False), "lineColor": col(PAPER), "transparency": d(100), "weight": d(0)}
    vl = {"show": b(True), "type": s(kind), "tooltip": s(tip)}
    vl[{"Bookmark": "bookmark", "WebUrl": "webUrl", "PageNavigation": "navigationSection"}[kind]] = s(target)
    v = {"visualType": "actionButton",
         "objects": {"icon": [obj(off, st) for st in states], "text": [obj(off, st) for st in states],
                     "fill": [obj(no_fill, st) for st in states], "outline": [obj(no_line, st) for st in states]},
         "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    v["visualContainerObjects"]["visualLink"] = [obj(vl)]
    return v


def footer_links(x_right, y, items, z, prefix="fl"):
    """Links to other pages at the right end of a footer, ending at x_right. items:
    (text, page or None, width in px); a linked item is underlined ink with a transparent
    page-navigation button over it, the rest is faint text. Widths are set by hand,
    from the rendered page: a text box cannot report its own."""
    V = []
    x = x_right - sum(w for _, _, w in items)
    for k, (text, page, w) in enumerate(items):
        # A text box trims its edge spaces, so a lone separator is centred in its own box.
        sep = text.strip() == "·"
        tb = textbox([[(text.strip(), 8.25, INK if page else FAINT, False)]], align="center" if sep else "left")
        if page:
            tb["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]["textStyle"]["textDecoration"] = "underline"
        V.append(container(f"{prefix}{k}t", x, y, w if sep else w + 6, 18, z, tb))
        if page:
            V.append(container(f"{prefix}{k}b", x, y, w, 18, z + 1, link_button(("PageNavigation", page), "Go to " + text)))
        x += w
    return V
