"""Report 1's theme for W21: defaults every page inherits, so a page only states
what differs. Replaces the theme of the old pages, which gave every visual a white
background and a rounded border - the boxes around buttons seen on 4 Nov 2026.

Fonts stay in the Segoe UI family: publish-to-web renders only the fonts Power BI
ships, so the mock-up's IBM Plex Sans is not available."""
import json, pathlib, sys

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report"
NAME = "NZ_Fuel_W21.json"
C = lambda h: {"solid": {"color": h}}
INK, MUTED, FAINT, RULE, BG = "#1B1B19", "#5C5B56", "#8A8983", "#ECEBE6", "#F7F7F5"

theme = {
    "name": "NZ fuel prices W21",
    "dataColors": [INK, "#2A78D6", "#EB6834", FAINT, "#40B54A", "#E5C700", "#4D4C48", "#C9C8C1", "#256ABF", "#D03B3B"],
    "background": "#FFFFFF", "foreground": INK, "tableAccent": "#2A78D6",
    "foregroundNeutralSecondary": MUTED, "foregroundNeutralTertiary": FAINT,
    "backgroundLight": BG, "backgroundNeutral": "#E6E5E0",
    "good": "#2A78D6", "neutral": FAINT, "bad": "#D03B3B",
    "textClasses": {
        "callout": {"fontSize": 21, "fontFace": "Segoe UI Semibold", "color": INK},
        "title": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": INK},
        "header": {"fontSize": 9, "fontFace": "Segoe UI Semibold", "color": MUTED},
        "label": {"fontSize": 8, "fontFace": "Segoe UI", "color": FAINT},
    },
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": False}],
            "border": [{"show": False}],
            "dropShadow": [{"show": False}],
            "visualHeader": [{"show": False}],
            "title": [{"show": False, "fontFamily": "Segoe UI Semibold", "fontColor": C(INK)}],
            "padding": [{"top": 0, "bottom": 0, "left": 0, "right": 0}],
            "visualTooltip": [{"fontSize": 9, "titleFontColor": C(MUTED), "valueFontColor": C(INK), "background": C("#FFFFFF")}],
            "categoryAxis": [{"fontSize": 7.5, "labelColor": C(FAINT), "showAxisTitle": False, "gridlineShow": False}],
            "valueAxis": [{"fontSize": 7.5, "labelColor": C(FAINT), "showAxisTitle": False,
                           "gridlineColor": C(RULE), "gridlineStyle": "solid"}],
            "legend": [{"show": False, "fontSize": 9, "labelColor": C(MUTED)}],
            "outspacePane": [{"titleSize": 11}],
        }},
        "page": {"*": {
            "background": [{"color": C(BG), "transparency": 0}],
            "outspace": [{"color": C(BG), "transparency": 0}],
        }},
        "pivotTable": {"*": {
            "grid": [{"gridHorizontal": False, "gridVertical": False}],
            "columnHeaders": [{"fontColor": C(FAINT), "fontSize": 8, "fontFamily": "Segoe UI"}],
            "values": [{"fontSize": 9}],
        }},
        "tableEx": {"*": {
            "grid": [{"gridHorizontal": True, "gridHorizontalColor": C(RULE), "gridVertical": False}],
            "columnHeaders": [{"fontColor": C(MUTED), "fontSize": 8, "fontFamily": "Segoe UI Semibold"}],
            "values": [{"fontSize": 9, "fontColorPrimary": C(INK)}],
        }},
    },
}
(ROOT / "StaticResources/RegisteredResources" / NAME).write_text(json.dumps(theme, indent=2) + "\n")
rep = json.loads((ROOT / "definition/report.json").read_text())
rep["themeCollection"]["customTheme"]["name"] = NAME
for pkg in rep["resourcePackages"]:
    if pkg["name"] == "RegisteredResources":
        pkg["items"] = [{"name": NAME, "path": NAME, "type": "CustomTheme"}]
(ROOT / "definition/report.json").write_text(json.dumps(rep, indent=2) + "\n")
print("theme", NAME)
