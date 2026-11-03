"""Small builders for PBIR JSON, so pages are written as code and rewritten whole."""
import json, pathlib, shutil

VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.11.0/schema.json"
PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"

INK, MUTED, FAINT, LINE, PAPER, BG = "#1B1B19", "#5C5B56", "#8A8983", "#E6E5E0", "#FFFFFF", "#F7F7F5"
CALL, CALL_LINE, ORANGE = "#256ABF", "#2A78D6", "#EB6834"
FONT, FONT_B = "Segoe UI", "Segoe UI Semibold"

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
    """An empty textbox whose container draws a rectangle: card backgrounds, rules, fuel underlines."""
    return {"visualType": "textbox", "objects": {"general": [obj({"paragraphs": []})]},
            "visualContainerObjects": chrome(background=background, border=border, radius=radius, padding=(0, 0, 0, 0)),
            "drillFilterOtherVisuals": True}

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

def title_shape(entity, measure, size, colour=INK, bold=True):
    """Long dynamic text: the title of an invisible shape, because a title wraps and a card value may not."""
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0), title_props={
                "show": b(True), "text": mexpr(entity, measure), "titleWrap": b(True),
                "fontSize": d(size), "fontFamily": s(FONT_B if bold else FONT), "fontColor": col(colour),
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
               background_measure=None, radius=None):
    """Short dynamic text, drawn as the title of an invisible shape. A new card does
    not draw its value in a container under ~30 px high (seen 4 Nov 2026); a title
    renders at any height and wraps."""
    tp = {"show": b(True), "text": mexpr(entity, measure), "titleWrap": b(True),
          "fontSize": d(size), "fontFamily": s(FONT_B if bold else FONT),
          "fontColor": mcol(*colour_measure) if colour_measure else col(colour),
          "alignment": s(align), "heading": s("Normal")}
    v = invisible_shape()
    v["visualContainerObjects"] = chrome(padding=(0, 0, 0, 0), title_props=tp)
    if background_measure:
        v["visualContainerObjects"]["background"] = [obj({"show": b(True), "color": mcol(*background_measure),
                                                          "transparency": d(0)})]
        v["visualContainerObjects"]["border"] = [obj({"show": b(True), "color": col(PAPER), "radius": d(radius or 0)})]
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
