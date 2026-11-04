"""Page 4, How it's built, written as PBIR: the weekly chain in four lanes, one box
per step, in the order the run takes them.

Static until W20, which gives each step its last run and the monthly bill. Until
then the times are typical ones, read off the runs of 22 and 29 Oct 2026, and the
page says nothing about the last run - on 29 Oct the archive step failed, and a
static "every step passed" would have been wrong that week.

Checked against .github/workflows/weekly.yml and Taskfile.yml on 4 Nov 2026. Two
things the mock-up of 20 Oct had wrong, corrected here: the cross-check against
Australian prices only warns - the gate is the one step that stops a run - and
not every one of the 43 tests has to pass: those under `monitoring` only warn."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pbir import *

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.Report/definition"
LANE_FILL, STEP_EDGE, BODY = "#EFEEEA", "#D9D8D2", "#4D4C48"
REPO = "https://github.com/AndRayFS/nz-fuel-price-azure-fabric"
STORY = "https://www.linkedin.com/posts/andreimor_watching-the-news-about-the-latest-escalation-ugcPost-7485572175953920001-Uzat/"
ZIP = "https://nzfueldata.blob.core.windows.net/data/latest/nz-fuel-latest.zip"

X0, X1 = 24, 1256                      # the lanes' left and right edges
LANES = [("Azure", "Logic App, Blob storage"),
         ("GitHub Actions", "Python, dbt, Taskfile"),
         ("Microsoft Fabric", "Lakehouse, Warehouse; awake only for the run"),
         ("Power BI", "PBIR and TMDL in git; publish to web")]
LANE_Y, LANE_H, LANE_GAP = 128, 96, 8
STEP_X, STEP_DX, STEP_W, STEP_H = 196, 108, 184, 84
# (lane, title, what it does, how long it takes)
STEPS = [(0, "Clock", "a Logic App starts the run every Thursday", "Thu 09:07 NZT"),
         (1, "Runner", "wakes the capacity, runs each step, then pauses it", "10–15 min in all"),
         (2, "Ingest", "a pipeline copies MBIE's file into the Lakehouse", "about 1 min"),
         (1, "Gate and cross-check", "no new MBIE week, no run; Australian prices only warn", "about 2 min"),
         (2, "dbt", "snapshot, silver and gold, then 43 data tests", "about 1½ min"),
         (1, "Model", "refits the ADL+ECM model at every week since 2013", "about 1½ min"),
         (2, "Report tables", "dbt rebuilds the calls and margin tables", "about 15 s"),
         (3, "This report", "the model is refreshed; the public page follows", "about 1 min"),
         (0, "Archive", "the same data as a dated zip in Blob storage", "after the refresh")]
TILES = [("43", "data tests every run; a failure outside monitoring stops it"),
         ("Since 2004", "weekly history, three fuels"),
         ("10–15 min", "of paid compute a week; the capacity sleeps otherwise"),
         # ~4.3 runs a month of ~15 min at the F2 rate measured in Aug 2026, NZ$0.729 an hour
         # (docs/cost_notes.md): NZ$0.78. The USD price is fixed; it moves with the exchange rate only.
         ("NZ$0.80", "a month of compute for about 4.3 weekly runs, plus storage")]

def lane_top(i): return LANE_Y + i * (LANE_H + LANE_GAP)

# Arrowheads are stacked bars, the same kind of rectangle as the line, so both land on
# the same pixels at whatever scale the page is shown. Glyphs (4 Nov) were centred as
# text and sat up to a pixel off some lines; a triangle shape draws nothing at all
# (both seen 5 Nov 2026). Five rows, 10 px wide at the base down to 2 at the tip.
HEAD_ROWS, HEAD_STEP = 5, 1.6
HEAD_H = HEAD_ROWS * HEAD_STEP

def arrow(name, x, y_from, y_to, z):
    """A vertical connector from one step's edge to the next one's, head at y_to."""
    down = y_to > y_from
    top, bottom = (y_from, y_to - HEAD_H + 1) if down else (y_to + HEAD_H - 1, y_from)
    V = [container(f"{name}l", x - 1, top, 2, bottom - top, z, blank(FAINT))]
    for k in range(HEAD_ROWS):
        w = 2 * (HEAD_ROWS - k) if down else 2 * (k + 1)       # widest row nearest the line
        y = (y_to - HEAD_H + k * HEAD_STEP) if down else (y_to + k * HEAD_STEP)
        V.append(container(f"{name}h{k}", x - w / 2, round(y, 1), w, 2, z + 1, blank(FAINT)))
    return V

def link_run(text, url):
    return {"value": text, "url": url, "textStyle": {"fontFamily": FONT, "fontSize": "9.75pt", "color": INK,
                                                       "textDecoration": "underline"}}

def page_built():
    V = header()
    V += [container("title", X0, 60, X1 - X0, 32, 100, textbox([[(
              "Every Thursday one chain, with no manual step, turns MBIE's file into this report", 17, INK, True)]])),
          container("sub", X0, 96, X1 - X0, 22, 101, textbox([[(
              "Between Thursdays nothing runs: the Fabric capacity sleeps, and the report is served from its published "
              "model.", 10.5, MUTED, False)]]))]

    z = 200
    for i, (name, tools) in enumerate(LANES):
        y = lane_top(i)
        V += [container(f"lane{i}", X0, y, X1 - X0, LANE_H, z + i, blank(LANE_FILL, border=LANE_FILL, radius=8)),
              container(f"lane{i}t", X0 + 12, y + 22, 150, 56, z + 10 + i, textbox([
                  [(name, 9.75, INK, True)], [(tools, 9, MUTED, False)]]))]

    z = 300
    boxes = []
    for k, (lane, title, what, when) in enumerate(STEPS):
        x, y = STEP_X + k * STEP_DX, lane_top(lane) + 6
        boxes.append((x, y))
        bg = blank(PAPER, border=INK if title == "This report" else STEP_EDGE, radius=8)
        if title == "This report":
            bg["visualContainerObjects"]["border"][0]["properties"]["width"] = d(2)
        V += [container(f"s{k}bg", x, y, STEP_W, STEP_H, z + k * 4, bg),
              container(f"s{k}t", x + 10, y + 6, STEP_W - 20, 54, z + k * 4 + 1, textbox([
                  [(title, 9.75, INK, True)], [(what, 9, BODY, False)]])),
              container(f"s{k}w", x + 10, y + STEP_H - 22, STEP_W - 20, 18, z + k * 4 + 2, textbox([
                  [(when, 8.25, MUTED, False)]]))]

    # Each arrow leaves one box and enters the next, at the middle of their overlap.
    z = 400
    for k in range(len(STEPS) - 1):
        (xa, ya), (xb, yb) = boxes[k], boxes[k + 1]
        x = xb + (xa + STEP_W - xb) // 2 if xb < xa + STEP_W else xb + 24
        if yb > ya: V += arrow(f"a{k}", x, ya + STEP_H, yb, z + k * 2)
        else:       V += arrow(f"a{k}", x, ya, yb + STEP_H, z + k * 2)

    z = 500
    tw = (X1 - X0) // 4
    for i, (big, small) in enumerate(TILES):
        x = X0 + i * tw
        V += [container(f"tile{i}b", x, 560, tw - 24, 34, z + i, textbox([[(big, 18, INK, True)]])),
              container(f"tile{i}s", x, 596, tw - 24, 36, z + 10 + i, textbox([[(small, 9.75, MUTED, False)]]))]

    plain = lambda t: {"value": t, "textStyle": {"fontFamily": FONT, "fontSize": "9.75pt", "color": MUTED}}
    links = {"visualType": "textbox", "objects": {"general": [obj({"paragraphs": [{"textRuns": [
                 plain("Code: "), link_run("GitHub repository", REPO),
                 plain("  ·  The story, step by step: "), link_run("LinkedIn series, from Part 1", STORY),
                 plain("  ·  Data: "), link_run("nz-fuel-latest.zip", ZIP), plain(", three CSV tables and a README")]}]})]},
             "visualContainerObjects": chrome(padding=(0, 0, 0, 0)), "drillFilterOtherVisuals": True}
    V.append(container("links", X0, 664, X1 - X0, 22, 600, links))
    return V

write_page(ROOT, "p4built", "How it's built", page_built())
pages = json.loads((ROOT / "pages/pages.json").read_text())
order = [p for p in pages["pageOrder"] if p != "p4built"]
order.insert(order.index("p3margin") + 1, "p4built")
pages["pageOrder"] = order
(ROOT / "pages/pages.json").write_text(json.dumps(pages, indent=2) + "\n")
print(len(page_built()), "visuals on How it's built")
