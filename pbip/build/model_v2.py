"""Write the W21 model additions as TMDL into the worktree. Re-runnable: lineage
tags are derived from names, so a rerun rewrites identical files."""
import uuid, sys, pathlib, textwrap

ROOT = pathlib.Path(sys.argv[1]) / "pbip/nz_fuel_v2.SemanticModel/definition"
NS = uuid.UUID("6f1c2d3e-0a4b-4c5d-8e9f-a1b2c3d4e5f6")
def tag(name): return str(uuid.uuid5(NS, name))

def block(text, depth):
    """Indent a multi-line DAX/M expression under a property, TMDL style."""
    pad = "\t" * depth
    return "\n".join(pad + l if l.strip() else "" for l in textwrap.dedent(text).strip("\n").split("\n"))

def measure(table, name, dax, fmt=None, desc=None, folder=None, hidden=False):
    q = f"'{name}'" if any(c in name for c in " ()%-/") else name
    out = []
    if desc:
        for line in desc.strip().split("\n"):
            out.append(f"\t/// {line}")
    if "\n" in dax.strip():
        out.append(f"\tmeasure {q} =")
        out.append(block(dax, 3))
    else:
        out.append(f"\tmeasure {q} = {dax.strip()}")
    if fmt: out.append(f"\t\tformatString: {fmt}")
    if folder: out.append(f"\t\tdisplayFolder: {folder}")
    if hidden: out.append("\t\tisHidden")
    out.append(f"\t\tlineageTag: {tag(table + '.m.' + name)}")
    return "\n".join(out) + "\n"

def column(table, name, dtype, fmt=None, calc=False, sort_by=None, hidden=False, summarize="none", date=False):
    q = f"'{name}'" if " " in name else name
    out = [f"\tcolumn {q}", f"\t\tdataType: {dtype}"]
    if fmt: out.append(f"\t\tformatString: {fmt}")
    if hidden: out.append("\t\tisHidden")
    out.append(f"\t\tlineageTag: {tag(table + '.c.' + name)}")
    out.append(f"\t\tsummarizeBy: {summarize}")
    if calc:
        out.append("\t\tisNameInferred")
        out.append(f"\t\tsourceColumn: [{name}]")
    else:
        out.append(f"\t\tsourceColumn: {name}")
    if sort_by: out.append(f"\t\tsortByColumn: '{sort_by}'" if " " in sort_by else f"\t\tsortByColumn: {sort_by}")
    out.append("")
    out.append("\t\tannotation SummarizationSetBy = Automatic")
    if date:
        out.append("")
        out.append("\t\tannotation UnderlyingDateTimeDataType = Date")
    return "\n".join(out) + "\n"

def calc_table(name, cols, dax, hidden=False):
    head = [f"table {name if ' ' not in name else repr(name)}"]
    if hidden: head.append("\tisHidden")
    head.append(f"\tlineageTag: {tag(name)}")
    body = "\n".join(head) + "\n\n" + "\n".join(cols)
    body += f"\n\tpartition {name if ' ' not in name else repr(name)} = calculated\n\t\tmode: import\n\t\tsource =\n{block(dax, 4)}\n\n\tannotation PBI_Id = {uuid.uuid5(NS, name + '.pbi').hex}\n"
    return body.replace(f"'{name}'", f"'{name}'")

WAREHOUSE = 'Sql.Database("fhi24zxnvquurfybnnzrkz22aq-ae4c5pcutjkedh2gfko4iqwk24.datawarehouse.fabric.microsoft.com", "analytics_warehouse")'

# ---------------------------------------------------------------- dimensions
fuel = calc_table("Fuel", [
    column("Fuel", "fuel", "string", calc=True),
    column("Fuel", "Fuel name", "string", calc=True, sort_by="Fuel order"),
    column("Fuel", "Fuel order", "int64", fmt="0", calc=True, hidden=True),
    column("Fuel", "Fuel colour", "string", calc=True, hidden=True),
], '''
DATATABLE(
    "fuel", STRING,
    "Fuel name", STRING,
    "Fuel order", INTEGER,
    "Fuel colour", STRING,
    {
        {"Regular Petrol", "Regular 91", 1, "#40B54A"},
        {"Premium Petrol 95R", "Premium 95", 2, "#E5C700"},
        {"Diesel", "Diesel", 3, "#4D4C48"}
    }
)''')

week = calc_table("Week", [
    column("Week", "week", "dateTime", fmt="d mmm yyyy", calc=True, date=True),
    column("Week", "Week short", "dateTime", fmt="d mmm", calc=True, date=True),
], '''
// Every Friday from MBIE's first week to five weeks past today. MBIE stamps each
// week by its Friday and the series has no gaps, so a generated calendar matches
// every week_date and target week without depending on the tables it filters.
VAR Fridays = GENERATESERIES(DATE(2004, 4, 23), TODAY() + 35, 7)
RETURN
    ADDCOLUMNS(
        SELECTCOLUMNS(Fridays, "week", [Value]),
        // The same date again, formatted without the year, for headers that
        // name the three called weeks. A text label would repeat every year and
        // could not be sorted by date.
        "Week short", [week]
    )''')

period = calc_table("Period", [
    column("Period", "Period", "string", calc=True, sort_by="Period order"),
    column("Period", "Weeks", "int64", fmt="0", calc=True, hidden=True),
    column("Period", "Period order", "int64", fmt="0", calc=True, hidden=True),
], '''
DATATABLE(
    "Period", STRING,
    "Weeks", INTEGER,
    "Period order", INTEGER,
    {
        {"3M", 13, 1},
        {"6M", 26, 2},
        {"1Y", 52, 3},
        {"5Y", 260, 4},
        {"2013+", 9999, 5}
    }
)''')

as_of = calc_table("As Of", [
    column("As Of", "As of week", "dateTime", fmt="d mmm yyyy", calc=True, date=True),
], '''
// For the hidden test page only: pick a past week and every page-1 measure,
// the headline included, is computed as if that week were the newest.
SELECTCOLUMNS(GENERATESERIES(DATE(2013, 2, 1), TODAY(), 7), "As of week", [Value])''', hidden=True)

# ---------------------------------------------------------------- prices
P = "prices"
pm = []
pm.append(measure(P, "Latest Week", '''
VAR Newest = CALCULATE(MAX(prices[week_date]), REMOVEFILTERS())
VAR AsOf = SELECTEDVALUE('As Of'[As of week])
RETURN IF(ISBLANK(AsOf), Newest, MIN(AsOf, Newest))''', fmt="d mmm yyyy", folder="Now",
    desc="The newest MBIE week in the model, whatever the visual filters. On the hidden test page, the week picked there instead."))
pm.append(measure(P, "Average Paid", "AVERAGE(prices[adjusted_retail_price])", fmt="0.0", folder="Now",
    desc="MBIE's national average price paid for the week, c/L. A few cents below the pump sign."))
pm.append(measure(P, "Price Now", '''
VAR W = [Latest Week]
RETURN CALCULATE([Average Paid], REMOVEFILTERS(Week), REMOVEFILTERS(prices[week_date]), prices[week_date] = W)''', fmt="0.0", folder="Now"))
pm.append(measure(P, "Price 4 Weeks Ago", '''
VAR W = [Latest Week] - 28
RETURN CALCULATE([Average Paid], REMOVEFILTERS(Week), REMOVEFILTERS(prices[week_date]), prices[week_date] = W)''', fmt="0.0", folder="Now"))
pm.append(measure(P, "Change 4w", '''
VAR NowP = [Price Now]
VAR ThenP = [Price 4 Weeks Ago]
RETURN IF(NOT ISBLANK(NowP) && NOT ISBLANK(ThenP), NowP - ThenP)''', fmt="+0.0;-0.0;0.0", folder="Now"))
pm.append(measure(P, "Change 4w %", "DIVIDE([Change 4w], [Price 4 Weeks Ago])", fmt="+0.0%;-0.0%;0.0%", folder="Now"))
pm.append(measure(P, "Price Now Label", '''IF(NOT ISBLANK([Price Now]), FORMAT([Price Now], "0.0") & " c/L")''', folder="Now"))
pm.append(measure(P, "Price Now Number", '''IF(NOT ISBLANK([Price Now]), FORMAT([Price Now], "0.0"))''', folder="Now",
    desc="The price without its unit: the card sets the number large and c/L small beside it, as the mock-up does."))
pm.append(measure(P, "Change 4w Main", '''
VAR vD = [Change 4w]
RETURN
IF(
    NOT ISBLANK(vD),
    FORMAT(vD, "+0.0;-0.0;0.0") & " c/L · " & FORMAT([Change 4w %], "+0.0%;-0.0%;0.0%")
)''', folder="Now", desc="The change itself, in ink and semibold as in the mock-up; the arrow beside it carries the colour, \"4 weeks\" sits after it in grey."))
pm.append(measure(P, "Change 4w Arrow", '''
VAR vD = [Change 4w]
RETURN IF(NOT ISBLANK(vD), IF(vD >= 0, "▲", "▼"))''', folder="Now"))
pm.append(measure(P, "Change 4w Label", '''
VAR D = [Change 4w]
RETURN
IF(
    NOT ISBLANK(D),
    IF(D >= 0, "▲ ", "▼ ") & FORMAT(D, "+0.0;-0.0;0.0") & " c/L · "
        & FORMAT([Change 4w %], "+0.0%;-0.0%;0.0%") & " · 4 weeks"
)''', folder="Now", desc="Gaspy-style change: arrow, c/L, per cent, and the window it covers."))
pm.append(measure(P, "Change 4w Colour", 'IF([Change 4w] >= 0, "#D03B3B", "#4D4C48")', folder="Now",
    desc="Rising price in red: it is the reader's cost. A fall stays neutral, not green - green is Regular 91's colour."))
pm.append(measure(P, "Change 4w Fill", 'IF([Change 4w] >= 0, "#FBE7E5", "#EFEEEA")', folder="Now"))
pm.append(measure(P, "Week To Label", '"Average paid, week to " & FORMAT([Latest Week], "d mmm")', folder="Now"))
pm.append(measure(P, "Header Weeks", '''
"Latest MBIE week: " & FORMAT([Latest Week], "d mmm yyyy")
    & " · next about " & FORMAT([Latest Week] + 13, "d mmm")''', folder="Now",
    desc="MBIE stamps a week by its Friday and publishes it the Wednesday after next; the chain loads it the Thursday, 13 days after the stamp."))
pm.append(measure(P, "Today", "TODAY()", fmt="d mmm yyyy", folder="Now",
    desc="For the Today line. Evaluated when the page is read, not at refresh, so it moves between loads."))
pm.append(measure(P, "In Period", '''
// Variables carry a v prefix: DAX inherits MDX's keywords, and the first
// version, with VARs named Weeks and Start, failed to parse in Desktop (4 Nov 2026).
VAR vWeek = MAX(Week[week])
VAR vLatest = [Latest Week]
VAR vWeeks = SELECTEDVALUE(Period[Weeks], 26)
VAR vFirst = IF(vWeeks >= 9999, DATE(2013, 2, 1), MAX(vLatest - 7 * vWeeks, DATE(2013, 2, 1)))
RETURN IF(vWeek > vFirst && vWeek <= vLatest + 21, 1)''', fmt="0", folder="Now",
    desc="Visual-level filter for page 1's charts: the chosen period up to the newest week, plus the three weeks the model has called. 2013+ starts at the first call, 1 Feb 2013."))
pm.append(measure(P, "Paid (chart)", '''
IF(MAX(Week[week]) <= [Latest Week] && [In Period] = 1, [Average Paid])''', fmt="0.0", folder="Now",
    desc="The period is applied here rather than as a visual filter on In Period: a measure filter written into PBIR broke the visual (Broken_Filters, 4 Nov 2026). Weeks where every series is blank drop off the axis by themselves."))
pm.append(measure(P, "Four Weeks Ago (chart)", '''
IF(MAX(Week[week]) = [Latest Week] - 28, [Average Paid])''', fmt="0.0", folder="Now",
    desc="One point, drawn as a hollow marker: where the four-week change is measured from."))
pm.append(measure(P, "Latest (chart)", """
IF(MAX(Week[week]) = [Latest Week], [Average Paid])""", fmt="0.0", folder="Now",
    desc="One point: the newest week, a dark dot where the calls leave from."))
pm.append(measure(P, "Four Weeks Ago Inner (chart)", "[Four Weeks Ago (chart)]", fmt="0.0", folder="Now",
    desc="The same point again, a smaller white marker over the dark one, so it reads as a hollow ring. Power BI line markers have no outline of their own."))
pm.append(measure(P, "Regular On Sign", """
VAR W = [Latest Week]
RETURN CALCULATE(AVERAGE(prices[board_price]), REMOVEFILTERS(), prices[week_date] = W, prices[fuel] = "Regular Petrol")""", fmt="0.0", folder="Now"))
pm.append(measure(P, "Now Footer", """
VAR W = [Latest Week]
VAR Sign = [Regular On Sign]
RETURN
"Average paid: MBIE's national average for the week, a few cents below the pump sign"
    & IF(NOT ISBLANK(Sign), " (Regular 91 showed " & FORMAT(Sign, "0.0") & " on the sign)", "")
    & ". MBIE publishes about a week later"
    & IF(TODAY() > W + 7, ", so " & FORMAT(W + 7, "d mmm") & " has passed but is not yet out", "")
    & ". Calls come from a walk-forward backtest model and are not published forecasts."
""", folder="Now"))
pm.append(measure(P, "Headline", r'''
// Two clauses, each a small decision table over the newest week's numbers.
// Mirrored in Python and run over every week since Feb 2013 before it was
// written here (W21). Change a threshold here and rerun that check.
VAR FLAT = 3      // c/L: a smaller four-week move counts as no move
VAR NEAR = 5      // c/L: a margin this close to its norm is "close to" it
VAR SPREAD = 5    // c/L: fuels further apart than this get a range, not one number
VAR W = [Latest Week]
VAR W4 = W - 28
VAR P91 = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W, prices[fuel] = "Regular Petrol")
VAR P95 = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W, prices[fuel] = "Premium Petrol 95R")
VAR PD = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W, prices[fuel] = "Diesel")
VAR Q91 = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W4, prices[fuel] = "Regular Petrol")
VAR Q95 = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W4, prices[fuel] = "Premium Petrol 95R")
VAR QD = CALCULATE(AVERAGE(prices[adjusted_retail_price]), REMOVEFILTERS(), prices[week_date] = W4, prices[fuel] = "Diesel")
VAR HavePrices = NOT (ISBLANK(P91) || ISBLANK(P95) || ISBLANK(PD) || ISBLANK(Q91) || ISBLANK(Q95) || ISBLANK(QD))
VAR D91 = P91 - Q91
VAR D95 = P95 - Q95
VAR DD = PD - QD
VAR DMin = MIN(MIN(D91, D95), DD)
VAR DMax = MAX(MAX(D91, D95), DD)
VAR NUp = (D91 >= FLAT) + (D95 >= FLAT) + (DD >= FLAT)
VAR NDown = (D91 <= -FLAT) + (D95 <= -FLAT) + (DD <= -FLAT)
VAR AmtUp = IF(DMax - DMin <= SPREAD, FORMAT((D91 + D95 + DD) / 3, "0"), FORMAT(DMin, "0") & "–" & FORMAT(DMax, "0"))
VAR AmtDown = IF(DMax - DMin <= SPREAD, FORMAT(-(D91 + D95 + DD) / 3, "0"), FORMAT(-DMax, "0") & "–" & FORMAT(-DMin, "0"))
VAR DPet = (D91 + D95) / 2
VAR VerbPet = IF(DPet >= FLAT, "rose " & FORMAT(ABS(DPet), "0") & " c/L", IF(DPet <= -FLAT, "fell " & FORMAT(ABS(DPet), "0") & " c/L", "held steady"))
VAR VerbDsl = IF(DD >= FLAT, "rose " & FORMAT(ABS(DD), "0") & " c/L", IF(DD <= -FLAT, "fell " & FORMAT(ABS(DD), "0") & " c/L", "held steady"))
VAR ClauseA =
    SWITCH(
        TRUE(),
        NOT HavePrices, "",
        NUp = 3, "Pump prices rose " & AmtUp & " c/L in four weeks.",
        NDown = 3, "Pump prices fell " & AmtDown & " c/L in four weeks.",
        NUp + NDown = 0, "Pump prices barely moved in four weeks.",
        VerbPet = VerbDsl,
            IF(VerbPet = "held steady", "Pump prices barely moved in four weeks.", "Pump prices " & VerbPet & " in four weeks."),
        "Petrol " & VerbPet & " in four weeks; diesel " & VerbDsl & "."
    )
// Clause B: the importer margin against its 104-week norm, c/L.
VAR M91 = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Regular Petrol")
VAR M95 = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Premium Petrol 95R")
VAR MD = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Diesel")
VAR N91 = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Regular Petrol")
VAR N95 = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Premium Petrol 95R")
VAR ND = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W, margin_compression[fuel] = "Diesel")
VAR M914 = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Regular Petrol")
VAR M954 = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Premium Petrol 95R")
VAR MD4 = CALCULATE(AVERAGE(margin_compression[importer_margin]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Diesel")
VAR N914 = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Regular Petrol")
VAR N954 = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Premium Petrol 95R")
VAR ND4 = CALCULATE(AVERAGE(margin_compression[margin_norm_104w]), REMOVEFILTERS(), margin_compression[week_date] = W4, margin_compression[fuel] = "Diesel")
VAR HaveMargins = NOT (ISBLANK(M91) || ISBLANK(M95) || ISBLANK(MD) || ISBLANK(N91) || ISBLANK(N95) || ISBLANK(ND))
VAR HaveMargins4 = NOT (ISBLANK(M914) || ISBLANK(M954) || ISBLANK(MD4) || ISBLANK(N914) || ISBLANK(N954) || ISBLANK(ND4))
VAR GPet = ((M91 - N91) + (M95 - N95)) / 2
VAR GDsl = MD - ND
VAR GPet4 = ((M914 - N914) + (M954 - N954)) / 2
VAR GDsl4 = MD4 - ND4
VAR SPet = IF(GPet <= -NEAR, "below", IF(GPet >= NEAR, "above", "near"))
VAR SDsl = IF(GDsl <= -NEAR, "below", IF(GDsl >= NEAR, "above", "near"))
VAR StillPet = HaveMargins4 && IF(GPet4 <= -NEAR, "below", IF(GPet4 >= NEAR, "above", "near")) = SPet
VAR StillDsl = HaveMargins4 && IF(GDsl4 <= -NEAR, "below", IF(GDsl4 >= NEAR, "above", "near")) = SDsl
VAR Lo = MIN(ABS(GPet), ABS(GDsl))
VAR Hi = MAX(ABS(GPet), ABS(GDsl))
VAR AmtBoth = IF(Hi - Lo <= SPREAD, "about " & FORMAT((Lo + Hi) / 2, "0"), FORMAT(Lo, "0") & "–" & FORMAT(Hi, "0"))
VAR PartPet =
    IF(
        SPet = "near",
        "Petrol's margin is close to its two-year average",
        "Petrol's margin is " & IF(StillPet, "still ", "") & "about " & FORMAT(ABS(GPet), "0") & " c/L " & SPet & " its two-year average"
    )
VAR PartDsl =
    IF(
        SDsl = "near",
        "diesel's is close to it",
        "diesel's is " & IF(StillDsl, "still ", "") & "about " & FORMAT(ABS(GDsl), "0") & " c/L " & SDsl & " it"
    )
VAR ClauseB =
    SWITCH(
        TRUE(),
        NOT HaveMargins, "",
        SPet = SDsl && SPet = "near", "Importer margins are close to their two-year average.",
        SPet = SDsl, "Importer margins are " & IF(StillPet && StillDsl, "still ", "") & AmtBoth & " c/L " & SPet & " their two-year average.",
        PartPet & "; " & PartDsl & "."
    )
RETURN
    ClauseA & IF(ClauseA <> "" && ClauseB <> "", " ", "") & ClauseB''', folder="Now",
    desc="Page 1's title, built from the newest week. States what happened and where margins stand - never what will happen."))

prices_cols = [
    column(P, "week_date", "dateTime", fmt="d mmm yyyy", date=True),
    column(P, "fuel", "string"),
    column(P, "adjusted_retail_price", "double", fmt="0.0"),
    column(P, "importer_cost", "double", fmt="0.0"),
    column(P, "importer_margin", "double", fmt="0.0"),
    column(P, "taxes", "double", fmt="0.0"),
    column(P, "ets", "double", fmt="0.0"),
    column(P, "gst", "double", fmt="0.0"),
    column(P, "board_price", "double", fmt="0.0"),
]
prices_m = f'''
let
    Source = {WAREHOUSE},
    silver_fuel = Source{{[Schema="dbo",Item="silver_fuel"]}}[Data],
    Kept = Table.SelectColumns(silver_fuel, {{"Date", "Fuel", "adjusted_retail_price", "importer_cost", "importer_margin", "taxes", "ets", "gst", "board_price"}}),
    Renamed = Table.RenameColumns(Kept, {{{{"Date", "week_date"}}, {{"Fuel", "fuel"}}}}),
    Typed = Table.TransformColumnTypes(Renamed, {{{{"week_date", type date}}, {{"fuel", type text}}, {{"adjusted_retail_price", type number}}, {{"importer_cost", type number}}, {{"importer_margin", type number}}, {{"taxes", type number}}, {{"ets", type number}}, {{"gst", type number}}, {{"board_price", type number}}}})
in
    Typed'''
prices = (f"/// MBIE's weekly price and its components, by fuel, straight from silver - the same rows the archive's weekly_prices.csv carries.\ntable prices\n\tlineageTag: {tag(P)}\n\n"
          + "\n".join(pm) + "\n" + "\n".join(prices_cols)
          + f"\n\tpartition prices = m\n\t\tmode: import\n\t\tsource =\n{block(prices_m, 4)}\n\n\tannotation PBI_ResultType = Table\n")

# ---------------------------------------------------------------- forecast_accuracy additions
F = "forecast_accuracy"
fm = []
fm.append(measure(F, "Call (chart)", '''
VAR W = MAX(Week[week])
VAR Latest = [Latest Week]
RETURN
SWITCH(
    TRUE(),
    W = Latest, [Average Paid],
    W > Latest && W <= Latest + 21,
        CALCULATE(AVERAGE(forecast_accuracy[pred_adl_ecm]), forecast_accuracy[week_date] = Latest)
)''', fmt="0.0", folder="Now",
    desc="The model's calls made in the newest week for the three weeks after it, starting from the last price paid so the line leaves from it."))
for name, q in (("Call Low (chart)", "0.25"), ("Call High (chart)", "0.75")):
    fm.append(measure(F, name, f'''
VAR vWeek = MAX(Week[week])
VAR vLatest = [Latest Week]
VAR vH = INT((vWeek - vLatest) / 7)
VAR vCall = [Call (chart)]
VAR vRegime =
    CALCULATE(
        MAX(forecast_accuracy[crude_vol_regime]),
        REMOVEFILTERS(Week), REMOVEFILTERS(Fuel),
        forecast_accuracy[week_date] = vLatest
    )
RETURN
IF(
    NOT ISBLANK(vCall),
    IF(
        vH = 0,
        vCall,
        // Only for the three called weeks, so the percentile never runs on an empty set.
        vCall
            + PERCENTILEX.INC(
                CALCULATETABLE(
                    forecast_accuracy,
                    REMOVEFILTERS(Week), REMOVEFILTERS(Fuel),
                    forecast_accuracy[crude_vol_regime] = vRegime,
                    forecast_accuracy[horizon_weeks] = vH,
                    forecast_accuracy[outcome_known] = TRUE(),
                    forecast_accuracy[Target week] <= vLatest
                ),
                forecast_accuracy[actual_price] - forecast_accuracy[pred_adl_ecm],
                {q}
            )
    )
)''', fmt="0.0", folder="Now",
        desc="Edge of the band around the calls: the call plus the " + ("25th" if q == "0.25" else "75th") + " percentile of past misses (actual minus call) at the same horizon, in weeks of the same crude-volatility regime as the newest, all three fuels pooled, outcomes known by the newest week. Agreed in the review of 19 Oct: the middle half of misses in weeks like this one, so the band widens when crude is volatile."))
for n in (1, 2, 3):
    fm.append(measure(F, f"Call Date {n}", f'''
VAR vLatest = [Latest Week]
RETURN IF(NOT ISBLANK(vLatest), FORMAT(vLatest + {7 * n}, "d mmm"))''', folder="Now",
        desc="The week the model's call is for, set over the number below it." if n == 1 else None))
    fm.append(measure(F, f"Call {n}", f'''
VAR vLatest = [Latest Week]
VAR vCall =
    CALCULATE(
        AVERAGE(forecast_accuracy[pred_adl_ecm]),
        REMOVEFILTERS(Week),
        forecast_accuracy[week_date] = vLatest,
        forecast_accuracy[horizon_weeks] = {n}
    )
RETURN IF(NOT ISBLANK(vCall), FORMAT(vCall, "0"))''', folder="Now",
        desc="The call made in the newest week for {n} week(s) ahead, in whole cents, as text so it can be set in a title. Three fixed slots replace the matrix, which bunched its columns to the left.".format(n=n) if n == 1 else None))
fm.append(measure(F, "Call Number", '''
VAR W = MAX(Week[week])
VAR Latest = [Latest Week]
RETURN IF(W > Latest && W <= Latest + 21, ROUND([Call (chart)], 0))''', fmt="0", folder="Now",
    desc="Whole cents: the model's error is several c/L, so a decimal would claim a precision it does not have."))

# ---------------------------------------------------------------- margin_compression additions
M = "margin_compression"
mm = []
for name, colname in (("Margin Now", "importer_margin"), ("Margin Norm Now", "margin_norm_104w")):
    mm.append(measure(M, name, f'''
VAR W = [Latest Week]
RETURN CALCULATE(AVERAGE(margin_compression[{colname}]), REMOVEFILTERS(Week), REMOVEFILTERS(margin_compression[week_date]), margin_compression[week_date] = W)''', fmt="0.0", folder="Now"))
mm.append(measure(M, "Track Full", '''
IF(NOT ISBLANK([Margin Now]), 60)''', fmt="0", folder="Now",
    desc="The grey track behind the cost pressure bar, 0-60 c/L as in the mock-up. Its own chart under the bar's: a stacked bar dropped both the colour measure and the norm's tick (4 Nov 2026)."))
mm.append(measure(M, "Margin Bar", '''
VAR vM = [Margin Now]
RETURN IF(NOT ISBLANK(vM), MAX(0, MIN(60, vM)))''', fmt="0.0", folder="Now",
    desc="Margin Now held to the 0-60 c/L track: a margin above 60 fills the bar, and the figures above it say by how much."))
mm.append(measure(M, "Margin Norm Bar", '''
VAR vN = [Margin Norm Now]
RETURN IF(NOT ISBLANK(vN), MAX(0, MIN(60, vN)))''', fmt="0.0", folder="Now",
    desc="Where the norm's tick sits on the same 0-60 c/L track."))
mm.append(measure(M, "Margin Gap Now", '''
VAR M = [Margin Now]
VAR N = [Margin Norm Now]
RETURN IF(NOT ISBLANK(M) && NOT ISBLANK(N), M - N)''', fmt="+0.0;-0.0;0.0", folder="Now"))
mm.append(measure(M, "Cost Pressure Label", '''
IF(NOT ISBLANK([Margin Gap Now]),
    FORMAT([Margin Now], "0.0") & " c/L now · average " & FORMAT([Margin Norm Now], "0.0"))''', folder="Now"))
mm.append(measure(M, "Cost Pressure Gap Label", '''
IF(NOT ISBLANK([Margin Gap Now]), FORMAT([Margin Gap Now], "+0.0;-0.0;0.0") & " c/L")''', folder="Now"))
mm.append(measure(M, "Cost Pressure Colour", '''
IF([Margin Gap Now] <= -5, "#EB6834", "#8A8983")''', folder="Now",
    desc="Orange when the margin sits at least 5 c/L under its norm: costs have run ahead of the pump. Same threshold as the headline's \"close to\"."))
mm.append(measure(M, "Cost Pressure Heading", '''
"Importer margin against its two-year average, week to " & FORMAT([Latest Week], "d mmm")
    & " · orange: below average, costs have run ahead of the pump"''', folder="Now"))

def append_measures(path, measures):
    text = path.read_text()
    marker = "\n\tcolumn "
    i = text.index(marker)
    start = "\n".join(measures)
    if all(m.split("\n")[0] in text for m in measures):
        return  # already there
    path.write_text(text[:i] + "\n" + start + text[i:])

(ROOT / "tables/Fuel.tmdl").write_text(fuel)
(ROOT / "tables/Week.tmdl").write_text(week)
(ROOT / "tables/Period.tmdl").write_text(period)
(ROOT / "tables/As Of.tmdl").write_text(as_of)
(ROOT / "tables/prices.tmdl").write_text(prices)
append_measures(ROOT / "tables/forecast_accuracy.tmdl", fm)
append_measures(ROOT / "tables/margin_compression.tmdl", mm)

rels = []
for frm, to in (("forecast_accuracy.fuel", "Fuel.fuel"), ("margin_compression.fuel", "Fuel.fuel"), ("prices.fuel", "Fuel.fuel"),
                ("forecast_accuracy.'Target week'", "Week.week"), ("margin_compression.week_date", "Week.week"), ("prices.week_date", "Week.week")):
    rels.append(f"relationship {tag('rel.' + frm)}\n\tfromColumn: {frm}\n\ttoColumn: {to}\n")
(ROOT / "relationships.tmdl").write_text("\n".join(rels))

model = (ROOT / "model.tmdl").read_text()
model = model.replace('annotation PBI_QueryOrder = ["forecast_accuracy","margin_compression"]',
                      'annotation PBI_QueryOrder = ["forecast_accuracy","margin_compression","prices"]')
if "ref table prices" not in model:
    model = model.replace("ref table margin_compression\n",
        "ref table margin_compression\nref table prices\nref table Fuel\nref table Week\nref table Period\nref table 'As Of'\n")
(ROOT / "model.tmdl").write_text(model)
print("written")
